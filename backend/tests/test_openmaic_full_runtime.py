from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
import json
import re
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from flask import Flask

from core.config import ConfigError, _validate_openmaic_full_runtime_config
from core.errors import ApiError
from integrations.openmaic_full_runtime_client import (
    OpenMaicFullRuntimeClient,
    OpenMaicFullRuntimeError,
)
from services.openmaic_full_runtime_service import (
    SAMPLE_GENERATION_STALE_AFTER_MS,
    SAMPLE_MODE,
    SAMPLE_REQUIRED_FEATURES,
    OpenMaicFullRuntimeService,
    OpenMaicRuntimeServiceError,
    _sample_boundary,
)
from services.openmaic_runtime_generation_runner import (
    OpenMaicRuntimeGenerationRunner,
)
from routes.internal import openmaic_runtime as openmaic_runtime_routes


class _HttpResponse:
    def __init__(
        self,
        payload: dict | None,
        url: str,
        *,
        raw: bytes | None = None,
        headers: dict[str, str] | None = None,
    ):
        self.payload = payload
        self.url = url
        self.raw = raw
        self.headers = headers or {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return self.url

    def read(self, _limit: int):
        if self.raw is not None:
            return self.raw[:_limit]
        return json.dumps(self.payload).encode("utf-8")


def _generated_agent(agent_id: str, role: str) -> dict:
    agent = {
        "id": agent_id,
        "name": "小数老师" if role == "teacher" else f"Agent {agent_id}",
        "role": role,
        "persona": "Warm primary-school classroom agent.",
        "avatar": f"/{agent_id}.png",
        "color": "#123456",
        "priority": 10 if role == "teacher" else 5,
    }
    if role == "teacher":
        agent["voiceConfig"] = {
            "providerId": "qwen-tts",
            "modelId": "qwen3-tts-flash",
            "voiceId": "Serena",
        }
    return agent


def _sample_course() -> dict:
    boundary = _sample_boundary()
    return {
        "course_id": "course-primary-1-math-number-sense-20",
        "course_version": "1",
        "release_id": "release-primary-1",
        "package_id": "package-number-sense-20",
        "package_version": 1,
        "public_content_hash": "a" * 64,
        "grade_code": "primary_1",
        "subject": "math",
        "node_code": "number_sense_20",
        "curriculum_version": boundary.curriculum_version,
        "boundary_version": boundary.boundary_version,
        "title": "20以内数感",
        "objective": "比较20以内数的大小，理解数的组成与顺序",
    }


def _sample_contract(service: OpenMaicFullRuntimeService) -> dict:
    return OpenMaicFullRuntimeService._sample_generation_contract(
        service,
        _sample_course(),
        boundary=_sample_boundary(),
    )


def _legacy_sample_contract(service: OpenMaicFullRuntimeService) -> dict:
    contract = deepcopy(_sample_contract(service))
    contract["schemaVersion"] = "mira.openmaic.sample-classroom.v1"
    contract["requiredClassroom"] = {
        "features": [
            "slides",
            "quiz",
            "simulation",
            "multi_agent_roundtable",
            "teacher_actions",
        ],
        "sceneTypes": ["slide", "quiz", "interactive"],
        "interactive": {
            "widgetType": "simulation",
            "widgetOutlineRequired": True,
        },
        "multiAgent": {
            "teacherRequired": True,
            "nonTeacherAgentRequired": True,
            "discussionActionRequired": True,
        },
        "teacherActionsRequired": True,
    }
    contract["speechAudioContract"].pop("requiredForEveryScene")
    contract["speechAudioContract"].pop("uniqueAudioRequired")
    contract.pop("conversationContract")
    return contract


def _sample_speech(index: int) -> dict:
    return {
        "id": f"speech-{index}",
        "type": "speech",
        "text": f"第 {index} 个场景的完整讲解。",
        "audioId": f"audio-{index}",
        "audioUrl": (
            "http://openmaic.internal:3000/api/classroom-media/"
            f"stage-1/media/audio/audio-{index}.mp3"
        ),
        "audioMetadata": {
            "schemaVersion": "mira.openmaic.speech-audio.v1",
            "providerId": "qwen-tts",
            "modelId": "qwen3-tts-flash",
            "voiceId": "Serena",
            "fallbackUsed": False,
        },
    }


def _complete_sample_widget_content(widget_type: str) -> dict:
    if widget_type == "simulation":
        config = {
            "type": "simulation",
            "concept": "number_comparison",
            "description": "拖动滑块观察数量变化",
            "variables": [
                {
                    "name": "count",
                    "label": "数量",
                    "min": 0,
                    "max": 20,
                    "default": 10,
                    "unit": "个",
                }
            ],
            "presets": [{"name": "十个", "variables": {"count": 10}}],
        }
        html = """
<!doctype html><html><body>
<input id="count-slider" data-var="count" type="range" min="0" max="20" value="10">
<output id="count-output">10</output><canvas id="simulation-canvas"></canvas>
<script>
const slider = document.getElementById('count-slider');
const output = document.getElementById('count-output');
const context = document.getElementById('simulation-canvas').getContext('2d');
function updateSimulation() {
  output.textContent = slider.value;
  context.clearRect(0, 0, 300, 150);
  context.fillRect(0, 0, Number(slider.value) * 5, 20);
}
slider.addEventListener('input', updateSimulation);
updateSimulation();
</script>
"""
    elif widget_type == "game":
        config = {
            "type": "game",
            "gameType": "number_train",
            "description": "按顺序把数字送上小火车",
            "gameConfig": {
                "controls": ["start_button"],
                "targets": [{"id": "train", "type": "number_slot"}],
                "initialConditions": {"score": 0, "level": 1},
                "successCondition": "score >= 20",
                "levels": [{"id": "level-1", "target": 10}],
            },
            "scoring": {"completionPoints": 20, "timeBonus": True},
            "achievements": [
                {
                    "id": "first_train",
                    "name": "发车啦",
                    "description": "完成第一关",
                }
            ],
        }
        html = """
<!doctype html><html><body>
<button id="start_button" type="button">开始</button>
<strong id="score-status">0</strong><canvas id="game-canvas"></canvas>
<script>
let score = 0;
let level = 1;
const scoreStatus = document.getElementById('score-status');
const gameContext = document.getElementById('game-canvas').getContext('2d');
function renderGame() {
  gameContext.clearRect(0, 0, 300, 150);
  gameContext.fillText(String(score), 20, 20);
}
document.getElementById('start_button').addEventListener('click', () => {
  score += 10;
  level++;
  scoreStatus.textContent = String(score);
  requestAnimationFrame(renderGame);
});
</script>
"""
    elif widget_type == "visualization3d":
        config = {
            "type": "visualization3d",
            "visualizationType": "number_blocks",
            "description": "旋转观察十个数量方块",
            "objects": [{"id": "number-block", "type": "box"}],
            "interactions": [{"type": "button", "action": "rotate"}],
        }
        html = """
<!doctype html><html><body>
<button id="rotate-button" type="button">旋转</button>
<canvas id="three-canvas"></canvas>
<script src="https://cdn.example.test/three.min.js"></script>
<script>
const canvas = document.getElementById('three-canvas');
const renderer = new THREE.WebGLRenderer({ canvas });
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 100);
const mesh = new THREE.Mesh(new THREE.BoxGeometry(), new THREE.MeshBasicMaterial());
scene.add(mesh);
function renderModel() { renderer.render(scene, camera); }
document.getElementById('rotate-button').addEventListener('click', () => {
  mesh.rotation.y += 0.25;
  renderModel();
});
renderModel();
</script>
"""
    else:
        raise AssertionError(f"unexpected sample widget type: {widget_type}")
    html += (
        '<script type="application/json" id="widget-config">'
        + json.dumps(config, ensure_ascii=False, separators=(",", ":"))
        + "</script></body></html>"
    )
    return {
        "type": "interactive",
        "html": html,
        "widgetType": widget_type,
        "widgetConfig": config,
    }


def _sample_parity_classroom() -> dict:
    classroom = _full_classroom()
    stage = classroom["stage"]
    stage["name"] = "20以内数感完整互动课堂"
    stage["generatedAgentConfigs"] = [
        _generated_agent("teacher-1", "teacher"),
        _generated_agent("student-1", "student"),
        _generated_agent("student-2", "student"),
        _generated_agent("student-3", "student"),
    ]
    original = classroom["scenes"]
    scenes = [deepcopy(scene) for scene in original[:5]]
    scenes.extend(
        [
            {
                "id": "slide-2",
                "stageId": "stage-1",
                "title": "数轴上的位置",
                "order": 5,
                "type": "slide",
                "content": {
                    "type": "slide",
                    "canvas": {
                        "elements": [{"id": "text-2", "type": "text"}],
                    },
                },
                "actions": [
                    {
                        "id": "spotlight-2",
                        "type": "spotlight",
                        "elementId": "text-2",
                    },
                    {
                        "id": "discussion-2",
                        "type": "discussion",
                        "topic": "谁能说出 12 和 15 的位置？",
                        "agentId": "student-2",
                    },
                ],
            },
            {
                **deepcopy(original[1]),
                "id": "simulation-2",
                "title": "数量比较实验",
                "order": 6,
                "actions": [],
            },
            {
                **deepcopy(original[2]),
                "id": "game-2",
                "title": "数字小火车",
                "order": 7,
                "actions": [],
            },
            {
                "id": "slide-3",
                "stageId": "stage-1",
                "title": "方法总结",
                "order": 8,
                "type": "slide",
                "content": {
                    "type": "slide",
                    "canvas": {
                        "elements": [{"id": "text-3", "type": "text"}],
                    },
                },
                "actions": [],
            },
            {
                **deepcopy(original[4]),
                "id": "quiz-2",
                "title": "独立检测",
                "order": 9,
                "actions": [],
            },
        ]
    )
    for index, scene in enumerate(scenes, start=1):
        scene["order"] = index - 1
        if scene["type"] == "interactive":
            scene["content"] = _complete_sample_widget_content(
                str(scene["content"]["widgetType"])
            )
        scene["actions"] = [
            action
            for action in scene.get("actions", [])
            if action.get("type") != "speech"
        ]
        scene["actions"].insert(0, _sample_speech(index))
    classroom["scenes"] = scenes
    return classroom


def _pbl_project() -> dict:
    return {
        "uiPhase": "hero",
        "title": "Build a phonics poster",
        "description": "Create and explain a small poster.",
        "tags": ["phonics"],
        "language": "zh-CN",
        "proficiency": "beginner",
        "status": "active",
        "roles": [
            {
                "id": "instructor-1",
                "type": "instructor",
                "name": "Teacher",
            }
        ],
        "milestones": [
            {
                "id": "milestone-1",
                "title": "Make the poster",
                "status": "active",
                "order": 0,
                "microtasks": [
                    {
                        "id": "microtask-1",
                        "title": "Place the first sound",
                        "status": "todo",
                        "assignee": "user",
                        "hints": [],
                        "order": 0,
                    }
                ],
            }
        ],
        "submissions": [],
        "evaluations": [],
        "threads": [{"agentId": "instructor-1", "messages": []}],
        "engagementEvents": [],
        "createdAt": "2026-08-14T00:00:00.000Z",
        "updatedAt": "2026-08-14T00:00:00.000Z",
    }


def _full_classroom() -> dict:
    stage_id = "stage-1"
    return {
        "stage": {
            "id": stage_id,
            "name": "Pinyin classroom",
            "createdAt": 1,
            "updatedAt": 2,
            "generatedAgentConfigs": [
                _generated_agent("teacher-1", "teacher"),
                _generated_agent("student-1", "student"),
            ],
        },
        "scenes": [
            {
                "id": "slide-1",
                "stageId": stage_id,
                "title": "Listen and watch",
                "order": 0,
                "type": "slide",
                "content": {
                    "type": "slide",
                    "canvas": {
                        "elements": [
                            {"id": "text-1", "type": "text"},
                            {
                                "id": "video-1",
                                "type": "video",
                                "src": (
                                    "http://openmaic.internal:3000/api/classroom-media/"
                                    "stage-1/media/video-1.mp4"
                                ),
                            },
                        ]
                    },
                },
                "actions": [
                    {
                        "id": "speech-1",
                        "type": "speech",
                        "text": "Listen.",
                        "audioId": "audio-1",
                        "audioUrl": (
                            "http://openmaic.internal:3000/api/classroom-media/"
                            "stage-1/media/audio/audio-1.mp3"
                        ),
                        "audioMetadata": {
                            "schemaVersion": "mira.openmaic.speech-audio.v1",
                            "providerId": "qwen-tts",
                            "modelId": "qwen3-tts-flash",
                            "voiceId": "Serena",
                            "fallbackUsed": False,
                        },
                    },
                    {
                        "id": "spotlight-1",
                        "type": "spotlight",
                        "elementId": "text-1",
                    },
                    {
                        "id": "video-action-1",
                        "type": "play_video",
                        "elementId": "video-1",
                    },
                    {
                        "id": "whiteboard-1",
                        "type": "wb_draw_text",
                        "content": "a o e",
                        "x": 100,
                        "y": 100,
                    },
                    {
                        "id": "discussion-1",
                        "type": "discussion",
                        "topic": "Which sound did you hear?",
                        "agentId": "student-1",
                    },
                ],
            },
            {
                "id": "simulation-1",
                "stageId": stage_id,
                "title": "Sound lab",
                "order": 1,
                "type": "interactive",
                "content": {
                    "type": "interactive",
                    "html": "<!doctype html><button id='sound'>Play</button>",
                    "widgetType": "simulation",
                    "widgetConfig": {"type": "simulation"},
                },
                "actions": [
                    {
                        "id": "widget-state-1",
                        "type": "widget_setState",
                        "state": {"sound": "a"},
                    }
                ],
            },
            {
                "id": "game-1",
                "stageId": stage_id,
                "title": "Sound game",
                "order": 2,
                "type": "interactive",
                "content": {
                    "type": "interactive",
                    "html": "<!doctype html><button>Choose</button>",
                    "widgetType": "game",
                    "widgetConfig": {"type": "game"},
                },
                "actions": [],
            },
            {
                "id": "3d-1",
                "stageId": stage_id,
                "title": "Mouth model",
                "order": 3,
                "type": "interactive",
                "content": {
                    "type": "interactive",
                    "html": "<!doctype html><canvas></canvas>",
                    "widgetType": "visualization3d",
                    "widgetConfig": {"type": "visualization3d"},
                },
                "actions": [],
            },
            {
                "id": "quiz-1",
                "stageId": stage_id,
                "title": "Check",
                "order": 4,
                "type": "quiz",
                "content": {
                    "type": "quiz",
                    "questions": [
                        {
                            "id": "question-1",
                            "type": "single",
                            "question": "Which one is a?",
                            "options": [
                                {"label": "a", "value": "A"},
                                {"label": "o", "value": "B"},
                            ],
                        }
                    ],
                },
                "actions": [],
            },
            {
                "id": "pbl-1",
                "stageId": stage_id,
                "title": "Poster project",
                "order": 5,
                "type": "pbl",
                "content": {"type": "pbl", "projectV2": _pbl_project()},
                "actions": [],
            },
        ],
    }


class _RuntimeClient:
    def __init__(self, *, media_available: bool = True, mp4_available: bool = True):
        self._media_available = media_available
        self._mp4_available = mp4_available

    def media_available(self, _reference, *, expected_prefix):
        return self._media_available and expected_prefix in {"audio/", "video/"}

    def video_export_capability(self):
        return self._mp4_available

    @staticmethod
    def sample_generation_readiness():
        return {
            "ready": True,
            "requiredVersion": "0.3.2",
            "reportedVersion": "0.3.2",
            "tts": True,
            "runtimePolicy": {
                "enforced": True,
                "providerId": "qwen-tts",
                "modelId": "qwen3-tts-flash",
                "voiceId": "Serena",
            },
            "asr": True,
            "asrPolicy": {
                "enforced": True,
                "providerId": "qwen-asr",
                "modelId": "qwen3-asr-flash",
                "fallbackAllowed": False,
            },
            "structuredScene": {
                "enforced": True,
                "policyId": "deepseek-v4-pro-flash-v1",
                "providerId": "deepseek",
                "modelId": "deepseek-v4-pro",
                "stages": [
                    "scene-content",
                    "scene-content:slide",
                    "scene-content:quiz",
                    "scene-content:interactive",
                    "scene-content:pbl",
                    "scene-actions",
                ],
                "thinking": {"mode": "disabled", "enabled": False},
            },
            "error": None,
        }

    @staticmethod
    def availability():
        return {"available": True, "baseUrlConfigured": True}


class _RetryRepository:
    def __init__(self, source: dict, course: dict):
        self.rows = {source["id"]: source}
        self.course = course
        self.write_count = 0
        self.mark_generating_result = True

    @contextmanager
    def transaction(self):
        yield object()

    @staticmethod
    def decode_json(value, _default):
        return value

    def get_by_request_id(self, _conn, *, request_id, **_kwargs):
        return next(
            (
                row
                for row in self.rows.values()
                if row["request_id"] == request_id
            ),
            None,
        )

    def get_runtime_classroom(self, _conn, *, runtime_id, **_kwargs):
        return self.rows.get(runtime_id)

    def get_active_release_course_for_boundary(self, _conn, **_kwargs):
        return self.course

    def get_package_runtime_attempts(
        self, _conn, *, package_id, package_version, **_kwargs
    ):
        return sorted(
            [
                row
                for row in self.rows.values()
                if row["package_id"] == package_id
                and int(row["package_version"]) == int(package_version)
            ],
            key=lambda row: int(row.get("attempt_ordinal") or 1),
        )

    def retire_runtime_for_retry(
        self, _conn, *, runtime_id, source_attempt_ordinal, now
    ):
        row = self.rows[runtime_id]
        if (
            row.get("retired_at") is not None
            or int(row.get("attempt_ordinal") or 0)
            != source_attempt_ordinal
            or row.get("status") != "failed"
        ):
            return False
        self.write_count += 1
        row["retired_at"] = now
        return True

    def create_retry_runtime_classroom(
        self,
        _conn,
        *,
        runtime_id,
        request_id,
        retry_of_runtime_id,
        retry_reason,
        expected_previous_job_id,
        attempt_ordinal,
        source_runtime,
        feature_manifest,
        now,
    ):
        self.write_count += 1
        row = {
            "id": runtime_id,
            "request_id": request_id,
            "attempt_ordinal": attempt_ordinal,
            "retry_of_runtime_id": retry_of_runtime_id,
            "retry_reason": retry_reason,
            "expected_previous_job_id": expected_previous_job_id,
            "course_id": source_runtime["course_id"],
            "course_version": source_runtime["course_version"],
            "package_id": source_runtime["package_id"],
            "package_version": source_runtime["package_version"],
            "status": "pending",
            "quality_status": "pending_review",
            "feature_manifest_json": feature_manifest,
            "upstream_job_id": None,
            "error_code": None,
            "ready_at": None,
            "retired_at": None,
            "created_at": now,
            "updated_at": now,
        }
        self.rows[runtime_id] = row
        return row

    def mark_generating(
        self, _conn, *, runtime_id, upstream_job_id, now
    ):
        if self.mark_generating_result is not True:
            return self.mark_generating_result
        self.write_count += 1
        self.rows[runtime_id].update(
            {
                "status": "generating",
                "upstream_job_id": upstream_job_id,
                "updated_at": now,
            }
        )
        return True

    def mark_failed(
        self, _conn, *, runtime_id, error_code, error_message_safe, now
    ):
        self.write_count += 1
        self.rows[runtime_id].update(
            {
                "status": "failed",
                "error_code": error_code,
                "error_message_safe": error_message_safe,
                "updated_at": now,
            }
        )


class _RetryClient(_RuntimeClient):
    def __init__(self):
        super().__init__()
        self.start_calls = 0
        self.readiness_calls = 0
        self.ready = True
        self.start_error = None
        self.on_start = None

    def sample_generation_readiness(self):
        self.readiness_calls += 1
        payload = super().sample_generation_readiness()
        if not self.ready:
            payload = {**payload, "ready": False, "error": "not-ready"}
        return payload

    def start_generation(self, **_kwargs):
        self.start_calls += 1
        if self.on_start is not None:
            self.on_start()
        if self.start_error is not None:
            raise self.start_error
        return SimpleNamespace(
            job_id=f"job-retry-{self.start_calls + 1}",
            status="queued",
            step="outline",
            progress=0,
            done=False,
        )


def _retry_service():
    service = object.__new__(OpenMaicFullRuntimeService)
    service.enabled = True
    service.generation_enabled = True
    service.public_url = "https://classroom.mira.test"
    service.video_export_enabled = False
    client = _RetryClient()
    service.client = client
    course = _sample_course()
    legacy_contract = _legacy_sample_contract(service)
    manifest = service._requested_manifest(
        legacy_contract["requiredClassroom"]["features"],
        legacy_contract["requiredClassroom"]["features"],
        generation_contract=legacy_contract,
    )
    source = {
        "id": "runtime-attempt-1",
        "request_id": "initial-request-1",
        "attempt_ordinal": 1,
        "retry_of_runtime_id": None,
        "retry_reason": None,
        "expected_previous_job_id": None,
        "course_id": course["course_id"],
        "course_version": course["course_version"],
        "package_id": course["package_id"],
        "package_version": course["package_version"],
        "status": "failed",
        "quality_status": "pending_review",
        "feature_manifest_json": manifest,
        "upstream_job_id": "job-attempt-1",
        "upstream_classroom_id": None,
        "error_code": "openmaic_sample_generation_stale",
        "error_message_safe": "stale",
        "ready_at": None,
        "retired_at": None,
        "created_at": 100,
        "updated_at": 200,
    }
    repository = _RetryRepository(source, course)
    service.repository = repository
    service._sample_generation_contract = (
        lambda _course, *, boundary: deepcopy(legacy_contract)
    )
    return service, repository, client


def _retry_service_with_failed_attempt_two():
    service, repository, client = _retry_service()
    service.retry_classroom(
        "runtime-attempt-1",
        {
            "retryRequestId": "approved-retry-2-for-attempt-3",
            "expectedPreviousJobId": "job-attempt-1",
            "reason": "approved_stage2_retry",
        },
    )
    service._sample_generation_contract = (
        OpenMaicFullRuntimeService._sample_generation_contract.__get__(
            service,
            OpenMaicFullRuntimeService,
        )
    )
    attempt_two = next(
        row for row in repository.rows.values() if row["attempt_ordinal"] == 2
    )
    attempt_two.update(
        {
            "status": "failed",
            "error_code": "openmaic_generation_process_restarted",
            "error_message_safe": "process restarted",
            "updated_at": 300,
        }
    )
    return service, repository, client, attempt_two


class OpenMaicFullRuntimeTest(unittest.TestCase):
    def test_sample_status_exposes_three_controlled_attempts_and_no_automatic_retry(self):
        service, _repository, _client = _retry_service()

        sample = service.status()["sample"]

        self.assertEqual(sample["maxAttempts"], 3)
        self.assertEqual(sample["manualRetries"], 2)
        self.assertEqual(sample["automaticRetries"], 0)

    def test_sample_readiness_requires_the_exact_health_contract_before_db(self):
        ready_policy = {
            "enforced": True,
            "providerId": "qwen-tts",
            "modelId": "qwen3-tts-flash",
            "voiceId": "Serena",
        }
        structured_scene_policy = {
            "enforced": True,
            "policyId": "deepseek-v4-pro-flash-v1",
            "providerId": "deepseek",
            "modelId": "deepseek-v4-pro",
            "stages": [
                "scene-content",
                "scene-content:slide",
                "scene-content:quiz",
                "scene-content:interactive",
                "scene-content:pbl",
                "scene-actions",
            ],
            "thinking": {"mode": "disabled", "enabled": False},
        }
        asr_policy = {
            "enforced": True,
            "providerId": "qwen-asr",
            "modelId": "qwen3-asr-flash",
            "fallbackAllowed": False,
        }
        base_health = {
            "success": True,
            "status": "ok",
            "version": "0.3.2",
            "capabilities": {"tts": True, "asr": True},
            "runtimePolicy": {
                "tts": ready_policy,
                "asr": asr_policy,
                "structuredScene": structured_scene_policy,
            },
        }
        invalid_health = {
            "missing-policy": {
                key: value
                for key, value in base_health.items()
                if key != "runtimePolicy"
            },
            "null-policy": {**base_health, "runtimePolicy": {"tts": None}},
            "wrong-policy": {
                **base_health,
                "runtimePolicy": {
                    "tts": {**ready_policy, "providerId": "macos-say"}
                },
            },
            "missing-structured-scene": {
                **base_health,
                "runtimePolicy": {"tts": ready_policy, "asr": asr_policy},
            },
            "wrong-structured-scene-model": {
                **base_health,
                "runtimePolicy": {
                    "tts": ready_policy,
                    "asr": asr_policy,
                    "structuredScene": {
                        **structured_scene_policy,
                        "modelId": "deepseek-v4-flash",
                    },
                },
            },
            "missing-scene-actions-policy": {
                **base_health,
                "runtimePolicy": {
                    **base_health["runtimePolicy"],
                    "structuredScene": {
                        **structured_scene_policy,
                        "stages": structured_scene_policy["stages"][:-1],
                    },
                },
            },
            "reordered-structured-scene-stages": {
                **base_health,
                "runtimePolicy": {
                    "tts": ready_policy,
                    "asr": asr_policy,
                    "structuredScene": {
                        **structured_scene_policy,
                        "stages": list(
                            reversed(structured_scene_policy["stages"])
                        ),
                    },
                },
            },
            "extra-structured-scene-field": {
                **base_health,
                "runtimePolicy": {
                    "tts": ready_policy,
                    "asr": asr_policy,
                    "structuredScene": {
                        **structured_scene_policy,
                        "baseUrl": "https://must-not-be-trusted.invalid",
                    },
                },
            },
            "tts-disabled": {
                **base_health,
                "capabilities": {"tts": False, "asr": True},
            },
            "asr-disabled": {
                **base_health,
                "capabilities": {"tts": True, "asr": False},
            },
            "wrong-asr-policy": {
                **base_health,
                "runtimePolicy": {
                    **base_health["runtimePolicy"],
                    "asr": {**asr_policy, "fallbackAllowed": True},
                },
            },
            "wrong-version": {**base_health, "version": "0.3.1"},
            "wrong-status": {**base_health, "status": "degraded"},
            "missing-success": {
                key: value for key, value in base_health.items() if key != "success"
            },
        }

        class Repository:
            def __init__(self):
                self.touched = False

            @contextmanager
            def transaction(self):
                self.touched = True
                raise AssertionError("unready runtime must not touch the database")
                yield object()

        for label, health in invalid_health.items():
            with self.subTest(label=label):
                calls = []

                def fake_urlopen(request, timeout):
                    self.assertEqual(timeout, 12.0)
                    calls.append(request.full_url)
                    return _HttpResponse(health, request.full_url)

                service = object.__new__(OpenMaicFullRuntimeService)
                service.enabled = True
                service.generation_enabled = True
                service.public_url = "https://classroom.mira.test"
                service.video_export_enabled = False
                service.repository = Repository()
                service.client = OpenMaicFullRuntimeClient(
                    "http://openmaic.internal:3000",
                    timeout_seconds=12,
                )
                with patch(
                    "integrations.openmaic_full_runtime_client.urlopen",
                    side_effect=fake_urlopen,
                ):
                    with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
                        service.generate_classroom(
                            {
                                "requestId": f"sample-{label}",
                                "sampleMode": SAMPLE_MODE,
                            }
                        )
                self.assertEqual(
                    raised.exception.code,
                    "openmaic_sample_generation_not_ready",
                )
                self.assertEqual(raised.exception.status_code, 503)
                self.assertFalse(service.repository.touched)
                self.assertEqual(
                    calls,
                    ["http://openmaic.internal:3000/api/health"],
                )

        client = OpenMaicFullRuntimeClient(
            "http://openmaic.internal:3000",
            timeout_seconds=12,
        )
        with patch(
            "integrations.openmaic_full_runtime_client.urlopen",
            return_value=_HttpResponse(
                base_health,
                "http://openmaic.internal:3000/api/health",
            ),
        ):
            readiness = client.sample_generation_readiness()
        self.assertTrue(readiness["ready"])
        self.assertEqual(readiness["runtimePolicy"], ready_policy)
        self.assertTrue(readiness["asr"])
        self.assertEqual(readiness["asrPolicy"], asr_policy)
        self.assertEqual(
            readiness["structuredScene"], structured_scene_policy
        )

    def test_status_exposes_only_non_secret_sample_readiness(self):
        service = object.__new__(OpenMaicFullRuntimeService)
        service.client = _RuntimeClient()
        service.enabled = True
        service.generation_enabled = True
        service.video_export_enabled = False
        status = service.status()
        readiness = status["sample"]["generationReadiness"]
        self.assertTrue(readiness["ready"])
        self.assertEqual(readiness["reportedVersion"], "0.3.2")
        self.assertEqual(readiness["runtimePolicy"]["providerId"], "qwen-tts")
        self.assertTrue(readiness["asr"])
        self.assertEqual(readiness["asrPolicy"]["providerId"], "qwen-asr")
        self.assertFalse(readiness["asrPolicy"]["fallbackAllowed"])
        self.assertEqual(
            readiness["structuredScene"]["policyId"],
            "deepseek-v4-pro-flash-v1",
        )
        self.assertNotIn("apiKey", json.dumps(readiness))

    def test_official_generation_and_poll_contracts_are_server_only(self):
        calls = []

        def fake_urlopen(request, timeout):
            calls.append((request, timeout))
            if request.full_url.endswith("/api/generate-classroom"):
                body = json.loads(request.data.decode("utf-8"))
                self.assertNotIn("apiKey", body)
                self.assertEqual(body["agentMode"], "generate")
                return _HttpResponse(
                    {
                        "success": True,
                        "jobId": "job_123",
                        "status": "queued",
                        "step": "outline",
                        "progress": 0,
                        "done": False,
                    },
                    request.full_url,
                )
            return _HttpResponse(
                {
                    "success": True,
                    "jobId": "job_123",
                    "status": "succeeded",
                    "step": "done",
                    "progress": 100,
                    "done": True,
                    "result": {
                        "classroomId": "classroom_123",
                        "scenesCount": 8,
                    },
                },
                request.full_url,
            )

        client = OpenMaicFullRuntimeClient(
            "http://openmaic.internal:3000", timeout_seconds=12
        )
        with patch(
            "integrations.openmaic_full_runtime_client.urlopen",
            side_effect=fake_urlopen,
        ):
            started = client.start_generation(
                requirement="一年级语文完整课堂",
                enable_web_search=False,
                enable_image_generation=True,
                enable_video_generation=True,
                enable_tts=False,
                agent_mode="generate",
            )
            completed = client.get_generation_job(started.job_id)

        self.assertEqual(started.status, "queued")
        self.assertEqual(completed.classroom_id, "classroom_123")
        self.assertEqual(completed.scenes_count, 8)
        self.assertEqual([call[1] for call in calls], [12.0, 12.0])

    def test_requirement_compiles_the_server_owned_sample_contract(self):
        service = object.__new__(OpenMaicFullRuntimeService)
        service.video_export_enabled = True
        service.client = _RuntimeClient()
        contract = _sample_contract(service)
        requirement = service._build_requirement(
            _sample_course(),
            SAMPLE_REQUIRED_FEATURES,
            required_features=SAMPLE_REQUIRED_FEATURES,
            generation_contract=contract,
        )
        self.assertNotIn("answer", requirement.casefold())
        self.assertIn("先教再练", requirement)
        self.assertIn("正式成绩由 Mira 后端判定", requirement)
        self.assertIn('"gradeCode":"primary_1"', requirement)
        self.assertIn('"skillId":"number_sense_20"', requirement)
        self.assertIn('"exactSceneCount":10', requirement)
        self.assertIn(
            "\nMIRA_OPENMAIC_SAMPLE_STRUCTURAL_POLICY_V1\n",
            f"\n{requirement}\n",
        )
        self.assertIn(
            '"requiredWidgetTypes":["simulation","game","visualization3d"]',
            requirement,
        )
        self.assertIn('"providerId":"qwen-tts"', requirement)
        self.assertIn('"modelId":"qwen3-tts-flash"', requirement)
        self.assertIn('"voiceId":"Serena"', requirement)
        self.assertIn("每个场景必须至少有一条", requirement)
        self.assertIn("小游戏或 3D", requirement)
        self.assertIn("qwen-asr/qwen3-asr-flash", requirement)

    def test_generic_manifest_still_detects_existing_runtime_features(self):
        service = object.__new__(OpenMaicFullRuntimeService)
        service.video_export_enabled = True
        service.client = _RuntimeClient()

        required = [
            "slides",
            "video",
            "3d_visualization",
            "simulation",
            "html_game",
            "pbl",
            "multi_agent_roundtable",
            "realtime_whiteboard",
            "teacher_actions",
        ]
        classroom = _full_classroom()
        for scene in classroom["scenes"]:
            if scene["type"] == "interactive":
                scene["content"] = _complete_sample_widget_content(
                    str(scene["content"]["widgetType"])
                )
        manifest = service._validate_and_manifest(
            classroom,
            requested=required,
            required=required,
        )
        self.assertEqual(manifest["schemaVersion"], "mira.openmaic.runtime-features.v2")
        self.assertTrue(set(required).issubset(set(manifest["present"])))
        self.assertIn("quiz", manifest["present"])
        self.assertEqual(manifest["missing"], [])
        self.assertEqual(manifest["enabled"], required)
        self.assertEqual(manifest["requested"], required)
        self.assertEqual(manifest["required"], required)
        self.assertTrue(manifest["evidence"]["video"]["verified"])
        self.assertTrue(manifest["evidence"]["teacher_actions"]["verified"])
        self.assertTrue(manifest["platform"]["mp4Export"])
        self.assertFalse(manifest["platform"]["mp4ExportClassroomDryRun"])
        self.assertNotIn("mp4_export", manifest["present"])

    def test_sample_manifest_requires_verified_qwen_audio_bytes_and_identity(self):
        service = object.__new__(OpenMaicFullRuntimeService)
        service.video_export_enabled = False
        service.client = _RuntimeClient()
        contract = _sample_contract(service)
        manifest = service._validate_and_manifest(
            _sample_parity_classroom(),
            requested=SAMPLE_REQUIRED_FEATURES,
            required=SAMPLE_REQUIRED_FEATURES,
            generation_contract=contract,
        )
        self.assertTrue(manifest["speechAudio"]["verified"])
        self.assertEqual(manifest["speechAudio"]["providerId"], "qwen-tts")
        self.assertEqual(manifest["speechAudio"]["modelId"], "qwen3-tts-flash")
        self.assertEqual(manifest["speechAudio"]["voiceId"], "Serena")
        self.assertEqual(manifest["speechAudio"]["verifiedAssetCount"], 10)
        self.assertEqual(manifest["speechAudio"]["speechActionCount"], 10)
        self.assertEqual(len(manifest["speechAudio"]["signals"]), 10)
        self.assertEqual(manifest["sceneCount"], 10)
        self.assertTrue(manifest["sceneNarration"]["verified"])
        self.assertEqual(manifest["sceneNarration"]["narratedSceneCount"], 10)
        self.assertEqual(manifest["sceneNarration"]["transcriptSceneCount"], 10)
        self.assertEqual(
            manifest["conversation"]["asr"],
            {
                "providerId": "qwen-asr",
                "modelId": "qwen3-asr-flash",
                "fallbackAllowed": False,
            },
        )
        self.assertTrue(manifest["teacherIdentity"]["verified"])
        # Static classroom/audio validation alone must never release the
        # sample; the gateway conversation probe supplies the final evidence.
        self.assertFalse(manifest["conversation"]["verified"])
        self.assertFalse(service._sample_manifest_verified(manifest))

        missing_metadata = deepcopy(_sample_parity_classroom())
        missing_metadata["scenes"][0]["actions"][0].pop("audioMetadata")
        with self.assertRaises(OpenMaicRuntimeServiceError) as missing:
            service._validate_and_manifest(
                missing_metadata,
                requested=SAMPLE_REQUIRED_FEATURES,
                required=SAMPLE_REQUIRED_FEATURES,
                generation_contract=contract,
            )
        self.assertEqual(missing.exception.code, "openmaic_sample_tts_identity_missing")

        fallback_audio = deepcopy(_sample_parity_classroom())
        fallback_audio["scenes"][0]["actions"][0]["audioMetadata"].update(
            {"providerId": "macos-say", "fallbackUsed": True}
        )
        with self.assertRaises(OpenMaicRuntimeServiceError) as fallback:
            service._validate_and_manifest(
                fallback_audio,
                requested=SAMPLE_REQUIRED_FEATURES,
                required=SAMPLE_REQUIRED_FEATURES,
                generation_contract=contract,
            )
        self.assertEqual(fallback.exception.code, "openmaic_sample_tts_identity_mismatch")

        service.client = _RuntimeClient(media_available=False)
        with self.assertRaises(OpenMaicRuntimeServiceError) as unreadable:
            service._validate_and_manifest(
                _sample_parity_classroom(),
                requested=SAMPLE_REQUIRED_FEATURES,
                required=SAMPLE_REQUIRED_FEATURES,
                generation_contract=contract,
            )
        self.assertEqual(unreadable.exception.code, "openmaic_sample_speech_audio_missing")

    def test_sample_parity_rejects_incomplete_scenes_interactions_agents_and_audio(self):
        service = object.__new__(OpenMaicFullRuntimeService)
        service.video_export_enabled = False
        service.client = _RuntimeClient()
        contract = _sample_contract(service)

        cases = []

        nine_scenes = _sample_parity_classroom()
        nine_scenes["scenes"].pop()
        cases.append(
            (nine_scenes, "openmaic_sample_scene_count_incomplete")
        )

        missing_narration = _sample_parity_classroom()
        missing_narration["scenes"][4]["actions"] = []
        cases.append(
            (missing_narration, "openmaic_sample_scene_narration_missing")
        )

        reused_audio = _sample_parity_classroom()
        reused_audio["scenes"][1]["actions"][0]["audioId"] = "audio-1"
        reused_audio["scenes"][1]["actions"][0]["audioUrl"] = (
            reused_audio["scenes"][0]["actions"][0]["audioUrl"]
        )
        cases.append((reused_audio, "openmaic_sample_speech_audio_reused"))

        too_few_peers = _sample_parity_classroom()
        too_few_peers["stage"]["generatedAgentConfigs"] = (
            too_few_peers["stage"]["generatedAgentConfigs"][:2]
        )
        cases.append((too_few_peers, "openmaic_sample_peer_agents_incomplete"))

        static_3d = _sample_parity_classroom()
        scene_3d = next(
            scene for scene in static_3d["scenes"] if scene["id"] == "3d-1"
        )
        scene_3d["content"]["html"] = "<!doctype html><p>静态 3D 占位文字</p>"
        cases.append((static_3d, "openmaic_sample_interactive_incomplete"))

        no_op_game = _sample_parity_classroom()
        game_scene = next(
            scene for scene in no_op_game["scenes"] if scene["id"] == "game-1"
        )
        game_config = game_scene["content"]["widgetConfig"]
        game_scene["content"]["html"] = (
            "<!doctype html><button id='decoy' type='button'>摆设按钮</button>"
            "<strong id='score-status'></strong>"
            "<script>const status=document.getElementById('score-status');"
            "status.textContent='0';"
            "document.getElementById('decoy').addEventListener('click',()=>{});"
            "requestAnimationFrame(()=>{});</script>"
            '<script type="application/json" id="widget-config">'
            + json.dumps(game_config, ensure_ascii=False, separators=(",", ":"))
            + "</script>"
        )
        cases.append((no_op_game, "openmaic_sample_interactive_incomplete"))

        incomplete_simulation_config = _sample_parity_classroom()
        simulation_scene = next(
            scene
            for scene in incomplete_simulation_config["scenes"]
            if scene["id"] == "simulation-1"
        )
        simulation_config = simulation_scene["content"]["widgetConfig"]
        simulation_config.pop("presets")
        simulation_scene["content"]["html"] = re.sub(
            r'(<script type="application/json" id="widget-config">)[\s\S]*?(</script>)',
            lambda match: (
                match.group(1)
                + json.dumps(
                    simulation_config,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + match.group(2)
            ),
            simulation_scene["content"]["html"],
        )
        cases.append(
            (
                incomplete_simulation_config,
                "openmaic_sample_interactive_incomplete",
            )
        )

        fake_webgl = _sample_parity_classroom()
        fake_3d_scene = next(
            scene for scene in fake_webgl["scenes"] if scene["id"] == "3d-1"
        )
        fake_3d_config = fake_3d_scene["content"]["widgetConfig"]
        fake_3d_scene["content"]["html"] = (
            "<!doctype html><button id='rotate'>旋转</button>"
            "<canvas id='model'></canvas>"
            "<script>const gl=document.getElementById('model').getContext('webgl');"
            "document.getElementById('rotate').addEventListener('click',()=>{"
            "document.getElementById('model').dataset.clicked='yes';});</script>"
            '<script type="application/json" id="widget-config">'
            + json.dumps(fake_3d_config, ensure_ascii=False, separators=(",", ":"))
            + "</script>"
        )
        cases.append((fake_webgl, "openmaic_sample_interactive_incomplete"))

        one_peer_discussion = _sample_parity_classroom()
        discussion_two = next(
            action
            for scene in one_peer_discussion["scenes"]
            for action in scene["actions"]
            if action.get("id") == "discussion-2"
        )
        discussion_two["agentId"] = "student-1"
        cases.append(
            (one_peer_discussion, "openmaic_sample_discussion_incomplete")
        )

        duplicate_order = _sample_parity_classroom()
        duplicate_order["scenes"][9]["order"] = 8
        cases.append((duplicate_order, "openmaic_sample_scene_order_invalid"))

        for classroom, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
                    service._validate_and_manifest(
                        classroom,
                        requested=SAMPLE_REQUIRED_FEATURES,
                        required=SAMPLE_REQUIRED_FEATURES,
                        generation_contract=contract,
                    )
                self.assertEqual(raised.exception.code, expected_code)

    def test_human_review_cannot_approve_an_unverified_sample_manifest(self):
        class Repository:
            def __init__(self):
                self.reviewed = False

            @contextmanager
            def transaction(self):
                yield object()

            @staticmethod
            def get_runtime_classroom(_conn, **_kwargs):
                return {
                    "id": "runtime-1",
                    "status": "ready",
                    "feature_manifest_json": {
                        "schemaVersion": "mira.openmaic.runtime-features.v2"
                    },
                }

            @staticmethod
            def decode_json(value, _default):
                return value

            def review_runtime_classroom(self, _conn, **_kwargs):
                self.reviewed = True
                raise AssertionError("invalid sample must not reach approval update")

        service = object.__new__(OpenMaicFullRuntimeService)
        service.repository = Repository()
        with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
            service.review_classroom(
                "runtime-1",
                {
                    "decision": "approve",
                    "reviewerId": "reviewer-1",
                    "notes": "",
                },
            )
        self.assertEqual(
            raised.exception.code, "openmaic_sample_contract_not_verified"
        )
        self.assertFalse(service.repository.reviewed)

    def test_interactive_kind_is_not_guessed_from_html_markers(self):
        classroom = _full_classroom()
        classroom["scenes"] = [
            {
                "id": "diagram-1",
                "stageId": "stage-1",
                "title": "Diagram",
                "order": 0,
                "type": "interactive",
                "content": {
                    "type": "interactive",
                    "html": "<!-- three.js simulation game webgl --><div>diagram</div>",
                    "widgetType": "diagram",
                    "widgetConfig": {"type": "diagram"},
                },
                "actions": [{"id": "speech-1", "type": "speech", "text": "Look."}],
            }
        ]
        service = object.__new__(OpenMaicFullRuntimeService)
        service.video_export_enabled = False
        service.client = _RuntimeClient()
        manifest = service._validate_and_manifest(
            classroom,
            requested=["simulation", "html_game", "3d_visualization", "teacher_actions"],
            required=["simulation", "html_game", "3d_visualization", "teacher_actions"],
        )
        self.assertEqual(manifest["present"], [])
        self.assertEqual(
            manifest["missing"],
            ["3d_visualization", "html_game", "simulation", "teacher_actions"],
        )

    def test_invalid_scene_and_hallucinated_action_fail_closed(self):
        service = object.__new__(OpenMaicFullRuntimeService)
        service.video_export_enabled = False
        service.client = _RuntimeClient()

        missing_content = _full_classroom()
        missing_content["scenes"][0].pop("content")
        with self.assertRaises(OpenMaicRuntimeServiceError) as scene_error:
            service._validate_and_manifest(missing_content, requested=["slides"])
        self.assertEqual(scene_error.exception.code, "invalid_openmaic_scene")

        invalid_action = _full_classroom()
        invalid_action["scenes"][0]["actions"] = [
            {"id": "fake-1", "type": "wb_draw", "content": "not in DSL"}
        ]
        with self.assertRaises(OpenMaicRuntimeServiceError) as action_error:
            service._validate_and_manifest(invalid_action, requested=["slides"])
        self.assertEqual(action_error.exception.code, "invalid_openmaic_action")

    def test_video_requires_same_scene_target_and_probed_media_bytes(self):
        service = object.__new__(OpenMaicFullRuntimeService)
        service.video_export_enabled = False
        service.client = _RuntimeClient(media_available=False)
        manifest = service._validate_and_manifest(
            _full_classroom(),
            requested=["video", "teacher_actions"],
            required=["video"],
        )
        self.assertNotIn("video", manifest["present"])
        self.assertEqual(manifest["missing"], ["video"])
        # Other independently proven UI operations still satisfy teacher_actions.
        self.assertIn("teacher_actions", manifest["present"])

        self.assertFalse(service._video_media_available("data:video/mp4;base64,"))
        self.assertTrue(
            service._video_media_available("data:video/mp4;base64,AAAA")
        )

    def test_repeated_video_reference_is_probed_once_per_classroom(self):
        class CountingClient(_RuntimeClient):
            def __init__(self):
                super().__init__()
                self.media_probe_count = 0

            def media_available(self, reference, *, expected_prefix):
                self.media_probe_count += 1
                return super().media_available(
                    reference, expected_prefix=expected_prefix
                )

        classroom = _full_classroom()
        classroom["scenes"][0]["actions"].append(
            {
                "id": "video-action-2",
                "type": "play_video",
                "elementId": "video-1",
            }
        )
        client = CountingClient()
        service = object.__new__(OpenMaicFullRuntimeService)
        service.video_export_enabled = False
        service.client = client

        manifest = service._validate_and_manifest(
            classroom,
            requested=["video"],
            required=["video"],
        )

        self.assertIn("video", manifest["present"])
        self.assertEqual(client.media_probe_count, 1)

    def test_widget_teacher_action_requires_embedded_runtime_handler(self):
        classroom = _full_classroom()
        classroom["scenes"] = [classroom["scenes"][1]]
        service = object.__new__(OpenMaicFullRuntimeService)
        service.video_export_enabled = False
        service.client = _RuntimeClient()

        classroom["scenes"][0]["content"]["html"] += "<!-- SET_WIDGET_STATE -->"
        missing_handler = service._validate_and_manifest(
            classroom,
            requested=["teacher_actions"],
            required=["teacher_actions"],
        )
        self.assertEqual(missing_handler["missing"], ["teacher_actions"])

        classroom["scenes"][0]["content"]["html"] += (
            "<script>window.addEventListener('message', e => "
            "e.data.type === 'SET_WIDGET_STATE')</script>"
        )
        with_handler = service._validate_and_manifest(
            classroom,
            requested=["teacher_actions"],
            required=["teacher_actions"],
        )
        self.assertIn("teacher_actions", with_handler["present"])

    def test_validation_bounds_actions_and_persisted_evidence(self):
        classroom = _full_classroom()
        slide = classroom["scenes"][0]
        slide["actions"] = [
            {
                "id": f"spotlight-{index}",
                "type": "spotlight",
                "elementId": "text-1",
            }
            for index in range(101)
        ]
        service = object.__new__(OpenMaicFullRuntimeService)
        service.video_export_enabled = False
        service.client = _RuntimeClient()

        manifest = service._validate_and_manifest(
            classroom,
            requested=["teacher_actions"],
            required=["teacher_actions"],
        )
        teacher_evidence = manifest["evidence"]["teacher_actions"]
        self.assertEqual(len(teacher_evidence["signals"]), 100)
        self.assertEqual(
            teacher_evidence["signals"][-1], "evidence-signals-truncated"
        )

        slide["actions"] = [
            {"id": f"speech-{index}", "type": "speech", "text": "hello"}
            for index in range(201)
        ]
        with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
            service._validate_and_manifest(classroom, requested=["slides"])
        self.assertEqual(raised.exception.code, "invalid_openmaic_actions")

    def test_mp4_is_platform_only_and_cannot_pass_without_classroom_dry_run(self):
        service = object.__new__(OpenMaicFullRuntimeService)
        service.video_export_enabled = True
        service.client = _RuntimeClient(mp4_available=True)
        manifest = service._validate_and_manifest(
            _full_classroom(),
            requested=["mp4_export"],
            required=["mp4_export"],
        )
        self.assertTrue(manifest["platform"]["mp4Export"])
        self.assertNotIn("mp4_export", manifest["present"])
        self.assertEqual(manifest["missing"], ["mp4_export"])
        self.assertFalse(manifest["evidence"]["mp4_export"]["verified"])

    def test_explicit_sample_rejects_all_browser_owned_context(self):
        service = object.__new__(OpenMaicFullRuntimeService)
        service.enabled = True
        service.generation_enabled = True
        service.public_url = "https://classroom.mira.test"
        service.client = object()
        with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
            service.generate_classroom(
                {
                    "requestId": "request-1",
                    "courseId": "course-1",
                    "courseVersion": "1",
                    "features": ["slides"],
                    "requiredFeatures": ["html_game"],
                }
            )
        self.assertEqual(raised.exception.code, "openmaic_sample_context_server_owned")

        with self.assertRaises(OpenMaicRuntimeServiceError) as wrong_mode:
            service.generate_classroom(
                {"requestId": "request-2", "sampleMode": "another-sample"}
            )
        self.assertEqual(wrong_mode.exception.code, "invalid_openmaic_sample_mode")

        service.video_export_enabled = False
        pending = service._requested_manifest(["slides"])
        self.assertEqual(pending["required"], [])
        self.assertEqual(pending["missing"], [])

    def test_explicit_sample_generation_is_single_and_idempotent(self):
        class Repository:
            def __init__(self):
                self.row = None
                self.boundary_query = None

            @contextmanager
            def transaction(self):
                yield object()

            def get_active_release_course_for_boundary(self, _conn, **kwargs):
                self.boundary_query = kwargs
                return _sample_course()

            def get_by_request_id(self, _conn, **_kwargs):
                return self.row

            @staticmethod
            def get_for_package(_conn, **_kwargs):
                return None

            def create_runtime_classroom(
                self,
                _conn,
                *,
                runtime_id,
                request_id,
                course,
                feature_manifest,
                now,
            ):
                self.row = {
                    "id": runtime_id,
                    "request_id": request_id,
                    "course_id": course["course_id"],
                    "course_version": course["course_version"],
                    "package_id": course["package_id"],
                    "package_version": course["package_version"],
                    "status": "pending",
                    "quality_status": "pending_review",
                    "feature_manifest_json": feature_manifest,
                    "ready_at": None,
                    "updated_at": now,
                }
                return self.row

            def mark_generating(
                self, _conn, *, runtime_id, upstream_job_id, now
            ):
                self.row.update(
                    {
                        "status": "generating",
                        "upstream_job_id": upstream_job_id,
                        "updated_at": now,
                    }
                )
                return True

            def get_runtime_classroom(self, _conn, *, runtime_id):
                self.assert_runtime_id = runtime_id
                return self.row

            @staticmethod
            def decode_json(value, _default):
                return value

        class Client:
            def __init__(self):
                self.calls = []
                self.readiness_calls = 0

            def start_generation(self, **kwargs):
                self.calls.append(kwargs)
                return SimpleNamespace(
                    job_id="job-sample-1",
                    status="queued",
                    step="outline",
                    progress=0,
                    done=False,
                )

            def sample_generation_readiness(self):
                self.readiness_calls += 1
                return _RuntimeClient.sample_generation_readiness()

        service = object.__new__(OpenMaicFullRuntimeService)
        service.enabled = True
        service.generation_enabled = True
        service.public_url = "https://classroom.mira.test"
        service.video_export_enabled = False
        service.repository = Repository()
        service.client = Client()

        payload = {"requestId": "sample-request-1", "sampleMode": SAMPLE_MODE}
        first = service.generate_classroom(payload)
        second = service.generate_classroom(payload)

        self.assertEqual(first["runtime"]["status"], "generating")
        self.assertEqual(second["runtime"]["id"], first["runtime"]["id"])
        self.assertEqual(len(service.client.calls), 1)
        self.assertEqual(service.client.readiness_calls, 2)
        self.assertEqual(
            service.repository.boundary_query["grade_code"], "primary_1"
        )
        call = service.client.calls[0]
        self.assertFalse(call["enable_web_search"])
        self.assertFalse(call["enable_image_generation"])
        self.assertFalse(call["enable_video_generation"])
        self.assertTrue(call["enable_tts"])
        self.assertEqual(call["agent_mode"], "generate")
        self.assertIn('"skillId":"number_sense_20"', call["requirement"])

    def test_controlled_retry_reserves_attempt_two_and_is_concurrently_idempotent(self):
        service, repository, client = _retry_service()
        request = {
            "retryRequestId": "approved-retry-2",
            "expectedPreviousJobId": "job-attempt-1",
            "reason": "approved_stage2_retry",
        }
        concurrent_results = []
        client.on_start = lambda: concurrent_results.append(
            service.retry_classroom("runtime-attempt-1", request)
        )

        first = service.retry_classroom("runtime-attempt-1", request)

        self.assertEqual(client.start_calls, 1)
        self.assertEqual(first["retry"]["attemptOrdinal"], 2)
        self.assertEqual(first["retry"]["status"], "generating")
        self.assertFalse(first["retry"]["idempotent"])
        self.assertEqual(concurrent_results[0]["retry"]["status"], "pending")
        self.assertTrue(concurrent_results[0]["retry"]["idempotent"])
        source = repository.rows["runtime-attempt-1"]
        self.assertEqual(source["upstream_job_id"], "job-attempt-1")
        self.assertEqual(source["error_code"], "openmaic_sample_generation_stale")
        self.assertIsNotNone(source["retired_at"])

    def test_third_controlled_generation_requires_attempt_two_and_is_idempotent(self):
        service, repository, client, attempt_two = (
            _retry_service_with_failed_attempt_two()
        )
        request = {
            "retryRequestId": "approved-retry-3",
            "expectedPreviousJobId": "job-retry-2",
            "reason": "approved_stage2_retry_3",
        }
        concurrent_results = []
        client.on_start = lambda: concurrent_results.append(
            service.retry_classroom(attempt_two["id"], request)
        )

        third = service.retry_classroom(attempt_two["id"], request)

        self.assertEqual(client.start_calls, 2)
        self.assertEqual(third["retry"]["attemptOrdinal"], 3)
        self.assertEqual(third["retry"]["attemptLimit"], 3)
        self.assertEqual(third["retry"]["status"], "generating")
        self.assertFalse(third["retry"]["idempotent"])
        self.assertEqual(concurrent_results[0]["retry"]["status"], "pending")
        self.assertTrue(concurrent_results[0]["retry"]["idempotent"])
        self.assertEqual(attempt_two["upstream_job_id"], "job-retry-2")
        self.assertEqual(
            attempt_two["error_code"],
            "openmaic_generation_process_restarted",
        )
        self.assertIsNotNone(attempt_two["retired_at"])
        attempts = sorted(
            repository.rows.values(), key=lambda row: row["attempt_ordinal"]
        )
        self.assertEqual(
            [row["attempt_ordinal"] for row in attempts], [1, 2, 3]
        )
        self.assertEqual(attempts[2]["retry_of_runtime_id"], attempt_two["id"])

        replay = service.retry_classroom(attempt_two["id"], request)
        self.assertTrue(replay["retry"]["idempotent"])
        self.assertEqual(client.start_calls, 2)

    def test_attempt_three_contract_upgrade_is_strictly_v1_to_server_v2(self):
        service, _repository, _client = _retry_service()
        legacy = _legacy_sample_contract(service)
        parity_v2 = _sample_contract(service)

        upgraded = service._attempt_three_upgraded_contract(
            legacy,
            parity_v2,
        )
        self.assertEqual(upgraded, parity_v2)

        changed_teacher = deepcopy(parity_v2)
        changed_teacher["teacher"]["profile"]["displayName"] = "other"
        self.assertIsNone(
            service._attempt_three_upgraded_contract(
                legacy,
                changed_teacher,
            )
        )

        unapproved_field = deepcopy(parity_v2)
        unapproved_field["modelOverride"] = "not-allowed"
        self.assertIsNone(
            service._attempt_three_upgraded_contract(
                legacy,
                unapproved_field,
            )
        )

    def test_third_controlled_generation_rejects_wrong_source_error_job_and_reason(self):
        cases = (
            (
                "error",
                "openmaic_sample_generation_stale",
                {
                    "retryRequestId": "retry-3-wrong-error",
                    "expectedPreviousJobId": "job-retry-2",
                    "reason": "approved_stage2_retry_3",
                },
                "openmaic_retry_not_allowed",
            ),
            (
                "job",
                None,
                {
                    "retryRequestId": "retry-3-wrong-job",
                    "expectedPreviousJobId": "different-job",
                    "reason": "approved_stage2_retry_3",
                },
                "openmaic_retry_previous_job_mismatch",
            ),
            (
                "reason",
                None,
                {
                    "retryRequestId": "retry-3-wrong-reason",
                    "expectedPreviousJobId": "job-retry-2",
                    "reason": "approved_stage2_retry",
                },
                "openmaic_retry_reason_invalid",
            ),
        )
        for label, forced_error, request, error_code in cases:
            with self.subTest(label=label):
                service, repository, client, attempt_two = (
                    _retry_service_with_failed_attempt_two()
                )
                if forced_error is not None:
                    attempt_two["error_code"] = forced_error
                writes_before = repository.write_count
                starts_before = client.start_calls
                with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
                    service.retry_classroom(attempt_two["id"], request)
                self.assertEqual(raised.exception.code, error_code)
                self.assertEqual(repository.write_count, writes_before)
                self.assertEqual(client.start_calls, starts_before)

    def test_attempt_four_and_different_third_key_are_rejected_without_model_call(self):
        service, _repository, client, attempt_two = (
            _retry_service_with_failed_attempt_two()
        )
        third_request = {
            "retryRequestId": "approved-retry-3-only",
            "expectedPreviousJobId": "job-retry-2",
            "reason": "approved_stage2_retry_3",
        }
        third = service.retry_classroom(attempt_two["id"], third_request)
        starts_after_third = client.start_calls

        with self.assertRaises(OpenMaicRuntimeServiceError) as different_key:
            service.retry_classroom(
                attempt_two["id"],
                {**third_request, "retryRequestId": "different-third-key"},
            )
        self.assertEqual(
            different_key.exception.code,
            "openmaic_retry_attempt_limit_reached",
        )

        with self.assertRaises(OpenMaicRuntimeServiceError) as fourth:
            service.retry_classroom(
                third["retry"]["runtimeId"],
                {
                    "retryRequestId": "forbidden-attempt-4",
                    "expectedPreviousJobId": "job-retry-3",
                    "reason": "approved_stage2_retry_3",
                },
            )
        self.assertEqual(fourth.exception.code, "openmaic_retry_not_allowed")
        self.assertEqual(client.start_calls, starts_after_third)

    def test_controlled_retry_route_requires_internal_token_and_forwards_exact_body(self):
        app = Flask(__name__)
        app.register_blueprint(
            openmaic_runtime_routes.internal_openmaic_runtime_bp,
            url_prefix="/internal/learning/openmaic",
        )

        class Guard:
            @staticmethod
            def authorize(*, headers, **_kwargs):
                if headers.get("X-Mira-Internal-Token") != "internal-secret":
                    raise ApiError(
                        "invalid_internal_token",
                        "内部调用未通过校验。",
                        401,
                    )
                return {"auditId": "audit-1", "sourceName": "test"}

        class Service:
            def __init__(self):
                self.calls = []

            def retry_classroom(self, runtime_id, data):
                self.calls.append((runtime_id, data))
                return {
                    "ok": True,
                    "retry": {
                        "runtimeId": "runtime-attempt-2",
                        "attemptOrdinal": 2,
                        "status": "pending",
                    },
                }

        service = Service()
        body = {
            "retryRequestId": "approved-retry-route",
            "expectedPreviousJobId": "job-attempt-1",
            "reason": "approved_stage2_retry",
        }
        with patch.object(
            openmaic_runtime_routes,
            "internal_request_guard",
            return_value=Guard(),
        ), patch.object(
            openmaic_runtime_routes,
            "openmaic_full_runtime_service",
            return_value=service,
        ):
            client = app.test_client()
            denied = client.post(
                "/internal/learning/openmaic/classrooms/runtime-attempt-1/retry",
                json=body,
            )
            accepted = client.post(
                "/internal/learning/openmaic/classrooms/runtime-attempt-1/retry",
                json=body,
                headers={"X-Mira-Internal-Token": "internal-secret"},
            )

        self.assertEqual(denied.status_code, 401)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(service.calls, [("runtime-attempt-1", body)])

    def test_controlled_retry_replay_survives_health_and_catalog_drift(self):
        service, repository, client = _retry_service()
        request = {
            "retryRequestId": "approved-retry-drift",
            "expectedPreviousJobId": "job-attempt-1",
            "reason": "approved_stage2_retry",
        }
        first = service.retry_classroom("runtime-attempt-1", request)
        first_readiness_calls = client.readiness_calls
        repository.course = None
        client.ready = False

        with patch(
            "services.openmaic_full_runtime_service.list_teacher_profiles",
            return_value=[],
        ):
            replay = service.retry_classroom("runtime-attempt-1", request)

        self.assertEqual(replay["retry"]["runtimeId"], first["retry"]["runtimeId"])
        self.assertTrue(replay["retry"]["idempotent"])
        self.assertEqual(client.start_calls, 1)
        self.assertEqual(client.readiness_calls, first_readiness_calls)

    def test_controlled_retry_validates_readiness_before_any_write_or_start(self):
        service, repository, client = _retry_service()
        client.ready = False
        with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
            service.retry_classroom(
                "runtime-attempt-1",
                {
                    "retryRequestId": "approved-retry-unready",
                    "expectedPreviousJobId": "job-attempt-1",
                    "reason": "approved_stage2_retry",
                },
            )
        self.assertEqual(
            raised.exception.code, "openmaic_sample_generation_not_ready"
        )
        self.assertEqual(repository.write_count, 0)
        self.assertEqual(client.start_calls, 0)

    def test_controlled_retry_rejects_invalid_contract_job_reason_and_third_attempt(self):
        cases = (
            (
                {"unexpected": True},
                "openmaic_retry_contract_invalid",
            ),
            (
                {
                    "retryRequestId": "retry-wrong-job",
                    "expectedPreviousJobId": "different-job",
                    "reason": "approved_stage2_retry",
                },
                "openmaic_retry_previous_job_mismatch",
            ),
            (
                {
                    "retryRequestId": "retry-wrong-reason",
                    "expectedPreviousJobId": "job-attempt-1",
                    "reason": "operator_retry",
                },
                "openmaic_retry_reason_invalid",
            ),
        )
        for request, error_code in cases:
            with self.subTest(error_code=error_code):
                service, repository, client = _retry_service()
                with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
                    service.retry_classroom("runtime-attempt-1", request)
                self.assertEqual(raised.exception.code, error_code)
                self.assertEqual(repository.write_count, 0)
                self.assertEqual(client.start_calls, 0)

        service, _repository, client = _retry_service()
        service.retry_classroom(
            "runtime-attempt-1",
            {
                "retryRequestId": "approved-retry-only",
                "expectedPreviousJobId": "job-attempt-1",
                "reason": "approved_stage2_retry",
            },
        )
        with self.assertRaises(OpenMaicRuntimeServiceError) as third:
            service.retry_classroom(
                "runtime-attempt-1",
                {
                    "retryRequestId": "forbidden-third-attempt",
                    "expectedPreviousJobId": "job-attempt-1",
                    "reason": "approved_stage2_retry",
                },
            )
        self.assertEqual(
            third.exception.code, "openmaic_retry_attempt_limit_reached"
        )
        self.assertEqual(client.start_calls, 1)

    def test_controlled_retry_start_failure_is_terminal_and_mark_failure_is_fail_closed(self):
        service, repository, client = _retry_service()
        client.start_error = OpenMaicFullRuntimeError(
            "openmaic_unavailable",
            "暂时无法连接 OpenMAIC 课堂服务",
            status_code=503,
        )
        request = {
            "retryRequestId": "approved-retry-start-failure",
            "expectedPreviousJobId": "job-attempt-1",
            "reason": "approved_stage2_retry",
        }
        with self.assertRaises(OpenMaicRuntimeServiceError):
            service.retry_classroom("runtime-attempt-1", request)
        attempt_two = next(
            row for row in repository.rows.values() if row["attempt_ordinal"] == 2
        )
        self.assertEqual(attempt_two["status"], "failed")
        self.assertEqual(attempt_two["error_code"], "openmaic_unavailable")
        replay = service.retry_classroom("runtime-attempt-1", request)
        self.assertEqual(replay["retry"]["status"], "failed")
        self.assertEqual(client.start_calls, 1)

        service, repository, client = _retry_service()
        repository.mark_generating_result = False
        uncertain_request = {
            "retryRequestId": "approved-retry-uncertain",
            "expectedPreviousJobId": "job-attempt-1",
            "reason": "approved_stage2_retry",
        }
        with self.assertRaises(OpenMaicRuntimeServiceError) as uncertain:
            service.retry_classroom("runtime-attempt-1", uncertain_request)
        self.assertEqual(
            uncertain.exception.code, "openmaic_generation_persistence_failed"
        )
        replay = service.retry_classroom(
            "runtime-attempt-1", uncertain_request
        )
        self.assertEqual(replay["retry"]["status"], "pending")
        self.assertEqual(client.start_calls, 1)

    def test_generation_status_marks_failed_when_required_feature_is_missing(self):
        classroom = _full_classroom()
        classroom["scenes"] = [classroom["scenes"][0]]

        class Client(_RuntimeClient):
            @staticmethod
            def get_generation_job(_job_id, *, formal=False):
                if formal:
                    raise AssertionError("this fixture covers a non-formal runtime job")
                return SimpleNamespace(
                    job_id="job-1",
                    status="succeeded",
                    step="done",
                    progress=100,
                    done=True,
                    classroom_id="classroom-1",
                    scenes_count=1,
                    error=None,
                )

            @staticmethod
            def get_classroom(_classroom_id):
                return classroom

        class Repository:
            def __init__(self):
                self.failed = None

            @contextmanager
            def transaction(self):
                yield object()

            @staticmethod
            def get_by_upstream_job(_conn, *, upstream_job_id):
                self.assertEqual(upstream_job_id, "job-1")
                return {
                    "id": "runtime-1",
                    "status": "generating",
                    "feature_manifest_json": {
                        "enabled": ["slides", "html_game"],
                        "requested": ["slides", "html_game"],
                        "required": ["slides", "html_game"],
                    },
                }

            @staticmethod
            def decode_json(value, _default):
                return value

            def mark_failed(self, _conn, **kwargs):
                self.failed = kwargs

            @staticmethod
            def mark_ready(_conn, **_kwargs):
                raise AssertionError("missing required features must never mark ready")

        service = object.__new__(OpenMaicFullRuntimeService)
        service.enabled = True
        service.generation_enabled = True
        service.public_url = "https://classroom.mira.test"
        service.video_export_enabled = False
        service.client = Client()
        service.repository = Repository()

        with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
            service.generation_status("job-1")
        self.assertEqual(raised.exception.code, "openmaic_required_features_missing")
        self.assertEqual(
            service.repository.failed["error_code"],
            "openmaic_required_features_missing",
        )

    def test_client_probes_video_export_and_same_origin_media(self):
        calls = []

        def fake_urlopen(request, timeout):
            calls.append((request.full_url, timeout))
            if request.full_url.endswith("/api/export-video/capability"):
                return _HttpResponse(
                    {"success": True, "enabled": True}, request.full_url
                )
            return _HttpResponse(
                None,
                request.full_url,
                raw=b"0",
                headers={"Content-Type": "video/mp4", "Content-Length": "42"},
            )

        client = OpenMaicFullRuntimeClient(
            "http://openmaic.internal:3000", timeout_seconds=12
        )
        with patch(
            "integrations.openmaic_full_runtime_client.urlopen",
            side_effect=fake_urlopen,
        ):
            self.assertTrue(client.video_export_capability())
            self.assertTrue(
                client.media_available(
                    "/api/classroom-media/stage-1/media/video.mp4",
                    expected_prefix="video/",
                )
            )
            self.assertFalse(
                client.media_available(
                    "https://untrusted.example/video.mp4",
                    expected_prefix="video/",
                )
            )
        self.assertEqual(len(calls), 2)

    def test_client_audio_probe_requires_supported_container_and_minimum_bytes(self):
        wav = b"RIFF" + (504).to_bytes(4, "little") + b"WAVE" + b"\x00" * 500
        mp3 = b"ID3" + b"\x04\x00\x00" + b"\x00" * 506
        invalid = b"not-audio" * 64
        truncated = b"RIFF\x00\x00\x00\x00WAVE"

        def fake_urlopen(request, timeout=None):
            del timeout
            if request.full_url.endswith("/valid.wav"):
                raw, content_type = wav, "audio/wav; charset=binary"
            elif request.full_url.endswith("/valid.mp3"):
                raw, content_type = mp3, "audio/mpeg"
            elif request.full_url.endswith("/truncated.wav"):
                raw, content_type = truncated, "audio/wav"
            else:
                raw, content_type = invalid, "audio/wav"
            return _HttpResponse(
                None,
                request.full_url,
                raw=raw,
                headers={
                    "Content-Type": content_type,
                    "Content-Length": str(len(raw)),
                },
            )

        client = OpenMaicFullRuntimeClient("http://openmaic.internal:3000")
        with patch(
            "integrations.openmaic_full_runtime_client.urlopen",
            side_effect=fake_urlopen,
        ):
            self.assertTrue(
                client.media_available("/valid.wav", expected_prefix="audio/")
            )
            self.assertTrue(
                client.media_available("/valid.mp3", expected_prefix="audio/")
            )
            self.assertFalse(
                client.media_available("/truncated.wav", expected_prefix="audio/")
            )
            self.assertFalse(
                client.media_available("/mislabeled.wav", expected_prefix="audio/")
            )

    def test_worker_never_scans_or_enqueues_the_active_release(self):
        class Repository:
            @contextmanager
            def transaction(self):
                yield object()

            @staticmethod
            def get_next_generating_runtime(_conn):
                return None

            @staticmethod
            def get_next_release_without_runtime(_conn):
                raise AssertionError("sample worker must never scan a release")

        service = object.__new__(OpenMaicFullRuntimeService)
        service.enabled = True
        service.generation_enabled = True
        service.client = object()
        service.public_url = "https://classroom.mira.test"
        service.repository = Repository()

        self.assertIsNone(service.process_next_pending())
        self.assertIsNone(service.process_next_pending())

    def test_worker_batch_reconciles_jobs_behind_one_rejection(self):
        rows = [
            {"id": "runtime-1"},
            {"id": "runtime-2"},
            {"id": "runtime-3"},
        ]

        class Repository:
            def __init__(self):
                self.requested_limit = None

            @contextmanager
            def transaction(self):
                yield object()

            def list_nonterminal_runtimes(self, _conn, *, limit):
                self.requested_limit = limit
                return rows

        visited = []

        def reconcile(runtime):
            runtime_id = runtime["id"]
            visited.append(runtime_id)
            if runtime_id == "runtime-2":
                raise OpenMaicRuntimeServiceError(
                    "openmaic_formal_required_features_missing",
                    "正式候选课堂未通过固定合同",
                    status_code=502,
                )
            return {
                "ok": True,
                "runtime": {
                    "id": runtime_id,
                    "status": (
                        "ready" if runtime_id == "runtime-1" else "generating"
                    ),
                },
            }

        service = object.__new__(OpenMaicFullRuntimeService)
        service.enabled = True
        service.generation_enabled = True
        service.client = object()
        service.public_url = "https://classroom.mira.test"
        service.repository = Repository()
        service._process_persisted_runtime = reconcile

        result = service.process_pending_batch(limit=30)

        self.assertEqual(visited, ["runtime-1", "runtime-2", "runtime-3"])
        self.assertEqual(service.repository.requested_limit, 30)
        self.assertEqual(result["processedCount"], 3)
        self.assertEqual(result["statusCounts"], {"ready": 1, "generating": 1})
        self.assertFalse(result["ok"])
        self.assertEqual(
            result["errors"][0]["code"],
            "openmaic_formal_required_features_missing",
        )

    def test_worker_terminally_fails_a_stale_sample_without_retry(self):
        timestamp = 2_000_000_000

        class Repository:
            def __init__(self):
                self.failed = None

            @contextmanager
            def transaction(self):
                yield object()

            @staticmethod
            def get_next_generating_runtime(_conn):
                return {
                    "id": "runtime-stale-1",
                    "request_id": "sample-request-stale",
                    "course_id": "course-primary-1-math-number-sense-20",
                    "course_version": "1",
                    "package_id": "package-number-sense-20",
                    "package_version": 1,
                    "status": "generating",
                    "quality_status": "pending_review",
                    "feature_manifest_json": {},
                    "ready_at": None,
                    "updated_at": timestamp - SAMPLE_GENERATION_STALE_AFTER_MS,
                }

            def mark_failed(self, _conn, **kwargs):
                self.failed = kwargs

            def get_runtime_classroom(self, _conn, *, runtime_id):
                return {
                    "id": runtime_id,
                    "request_id": "sample-request-stale",
                    "course_id": "course-primary-1-math-number-sense-20",
                    "course_version": "1",
                    "package_id": "package-number-sense-20",
                    "package_version": 1,
                    "status": "failed",
                    "quality_status": "pending_review",
                    "feature_manifest_json": {},
                    "ready_at": None,
                    "updated_at": timestamp,
                }

            @staticmethod
            def decode_json(value, _default):
                return value

        class Client:
            @staticmethod
            def get_generation_job(_job_id):
                raise AssertionError("stale task must not call OpenMAIC")

        service = object.__new__(OpenMaicFullRuntimeService)
        service.enabled = True
        service.generation_enabled = True
        service.client = Client()
        service.public_url = "https://classroom.mira.test"
        service.repository = Repository()

        with patch(
            "services.openmaic_full_runtime_service.now_ms",
            return_value=timestamp,
        ):
            result = service.process_next_pending()
        self.assertEqual(result["runtime"]["status"], "failed")
        self.assertEqual(
            service.repository.failed["error_code"],
            "openmaic_sample_generation_stale",
        )

    def test_runner_records_safe_state_without_swallowing_test_errors(self):
        runner = OpenMaicRuntimeGenerationRunner()
        result = runner.run_once(
            process_next=lambda: {
                "ok": True,
                "runtime": {"id": "runtime-1", "status": "generating"},
            },
            checked_at_ms=42,
        )
        self.assertEqual(result["runtime"]["status"], "generating")
        self.assertEqual(runner.status()["lastRuntimeId"], "runtime-1")
        self.assertEqual(runner.status()["lastCheckedAt"], 42)

    def test_runner_requires_the_separate_autorun_switch(self):
        runner = OpenMaicRuntimeGenerationRunner()
        app = SimpleNamespace(
            config={
                "OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED": True,
                "OPENMAIC_FULL_RUNTIME_AUTORUN_ENABLED": False,
                "TESTING": False,
            }
        )
        with patch("services.openmaic_runtime_generation_runner.threading.Thread") as thread:
            runner.start(app)
        thread.assert_not_called()
        self.assertIsNone(runner._thread)

    def test_student_launch_is_blocked_until_human_quality_review(self):
        class Auth:
            @staticmethod
            def authenticate(_token):
                return {
                    "principal": {
                        "id": "student-1",
                        "family_id": "family-1",
                        "child_id": "child-1",
                    }
                }

        class Repository:
            @contextmanager
            def transaction(self):
                yield object()

            @staticmethod
            def get_owned_session_runtime(_conn, **_kwargs):
                return {
                    "child_grade_code": "primary_1",
                    "course_grade_code": "primary_1",
                    "course_subject": "math",
                    "course_node_code": "number_sense_20",
                    "runtime_classroom_id": "runtime-1",
                    "runtime_status": "ready",
                    "runtime_quality_status": "pending_review",
                    "upstream_classroom_id": "classroom-1",
                }

        service = object.__new__(OpenMaicFullRuntimeService)
        service.enabled = True
        service.client = object()
        service.public_url = "https://classroom.mira.test"
        service.student_auth_service = Auth()
        service.repository = Repository()

        with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
            service.create_student_launch("student-access", "session-1")
        self.assertEqual(raised.exception.code, "openmaic_runtime_review_pending")
        self.assertEqual(raised.exception.status_code, 409)

    def test_student_launch_uses_authenticated_child_grade(self):
        class Auth:
            @staticmethod
            def authenticate(_token):
                return {
                    "principal": {
                        "id": "student-1",
                        "family_id": "family-1",
                        "child_id": "child-1",
                    }
                }

        class Repository:
            @contextmanager
            def transaction(self):
                yield object()

            @staticmethod
            def get_owned_session_runtime(_conn, **_kwargs):
                return {
                    "child_grade_code": "primary_2",
                    "course_grade_code": "primary_1",
                    "course_subject": "math",
                    "course_node_code": "number_sense_20",
                    "runtime_classroom_id": "runtime-1",
                    "runtime_status": "ready",
                    "runtime_quality_status": "approved",
                    "upstream_classroom_id": "classroom-1",
                }

        service = object.__new__(OpenMaicFullRuntimeService)
        service.enabled = True
        service.client = object()
        service.public_url = "https://classroom.mira.test"
        service.student_auth_service = Auth()
        service.repository = Repository()

        with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
            service.create_student_launch("student-access", "session-1")
        self.assertEqual(raised.exception.code, "openmaic_student_grade_mismatch")

    def test_exchange_and_runtime_session_recheck_the_verified_manifest(self):
        class Repository:
            def __init__(self):
                self.consumed = False
                self.touched = False

            @contextmanager
            def transaction(self):
                yield object()

            @staticmethod
            def get_launch_ticket_for_update(_conn, **_kwargs):
                return {
                    "id": "ticket-1",
                    "learning_session_id": "session-1",
                    "expires_at": 9_999_999_999_999,
                    "revoked_at": None,
                    "consumed_at": None,
                    "runtime_status": "ready",
                    "runtime_quality_status": "approved",
                    "upstream_classroom_id": "classroom-1",
                    "feature_manifest_json": {},
                }

            @staticmethod
            def get_runtime_session_for_update(_conn, **_kwargs):
                return {
                    "id": "runtime-session-1",
                    "learning_session_id": "session-1",
                    "expires_at": 9_999_999_999_999,
                    "revoked_at": None,
                    "runtime_status": "ready",
                    "runtime_quality_status": "approved",
                    "upstream_classroom_id": "classroom-1",
                    "feature_manifest_json": {},
                }

            @staticmethod
            def decode_json(value, _default):
                return value

            def consume_launch_ticket(self, _conn, **_kwargs):
                self.consumed = True

            def touch_runtime_session(self, _conn, **_kwargs):
                self.touched = True

        service = object.__new__(OpenMaicFullRuntimeService)
        service.enabled = True
        service.client = object()
        service.public_url = "https://classroom.mira.test"
        service.session_ttl_seconds = 3600
        service.repository = Repository()

        with self.assertRaises(OpenMaicRuntimeServiceError) as exchange:
            service.exchange_launch_ticket("ticket-token-1")
        self.assertEqual(
            exchange.exception.code, "openmaic_sample_contract_not_verified"
        )
        self.assertFalse(service.repository.consumed)

        with self.assertRaises(OpenMaicRuntimeServiceError) as validate:
            service.validate_runtime_session("runtime-token-1")
        self.assertEqual(
            validate.exception.code, "openmaic_sample_contract_not_verified"
        )
        self.assertFalse(service.repository.touched)

    def test_config_keeps_external_generation_explicit_and_public_https(self):
        with self.assertRaises(ConfigError):
            _validate_openmaic_full_runtime_config(
                app_env="development",
                enabled=False,
                generation_enabled=True,
                generation_interval_seconds=20,
                internal_url="",
                public_url="",
                timeout_seconds=30,
                launch_ttl_seconds=60,
                session_ttl_seconds=3600,
            )
        with self.assertRaises(ConfigError):
            _validate_openmaic_full_runtime_config(
                app_env="development",
                enabled=True,
                generation_enabled=False,
                autorun_enabled=True,
                generation_interval_seconds=20,
                internal_url="http://openmaic:3000",
                public_url="http://127.0.0.1:3101",
                timeout_seconds=30,
                launch_ttl_seconds=60,
                session_ttl_seconds=3600,
            )
        with self.assertRaises(ConfigError):
            _validate_openmaic_full_runtime_config(
                app_env="production",
                enabled=True,
                generation_enabled=False,
                generation_interval_seconds=20,
                internal_url="http://openmaic:3000",
                public_url="http://classroom.example.com",
                timeout_seconds=30,
                launch_ttl_seconds=60,
                session_ttl_seconds=3600,
            )


if __name__ == "__main__":
    unittest.main()
