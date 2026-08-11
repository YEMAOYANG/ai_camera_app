from __future__ import annotations

import json
import unittest
from contextlib import contextmanager
from types import SimpleNamespace

from integrations.camera_runtime.base import CameraSnapshot
from services.bound_camera_observation_service import (
    BoundCameraObservationConfig,
    BoundCameraObservationService,
)
from services.camera_observe_service import ObserveTickResult
from services.observation_runtime_state import ObservationRuntimeStateStore
from workers.camera_observation_worker import CameraObservationWorker


class BoundCameraObservationServiceTest(unittest.TestCase):
    def test_offline_device_does_not_block_next_bound_device(self):
        repository = _DeviceRepository(
            [
                {"family_id": "fam_1", "device_id": "dev_1"},
                {"family_id": "fam_1", "device_id": "dev_2"},
            ]
        )
        profile = _ProfileRepository(
            children={"fam_1": [{"id": "child_1"}]},
            privacy={"fam_1": _authorized_privacy()},
        )
        resolver = _RuntimeResolver(failing_devices={"dev_1"})
        observe = _ObserveService()
        adapter = _service(
            repository=repository,
            profile=profile,
            resolver=resolver,
            observe=observe,
        )

        result = adapter.run_observe_tick(
            window_start_ms=1_000,
            window_end_ms=2_000,
        )

        self.assertEqual(result["processed_count"], 2)
        self.assertEqual(result["observation_count"], 1)
        self.assertEqual(result["posted_count"], 1)
        self.assertEqual(result["skip_reasons"]["device_unavailable"], 1)
        self.assertEqual(resolver.calls, [("fam_1", "dev_1"), ("fam_1", "dev_2")])
        self.assertEqual(observe.calls[0]["child_id"], "child_1")
        self.assertEqual(observe.calls[0]["device_id"], "dev_2")
        self.assertEqual(observe.calls[0]["content_type"], "image/png")
        self.assertEqual(observe.calls[0]["source"], "camera_observation_worker")
        self.assertNotIn("post_observation", observe.calls[0])
        self.assertNotIn("rtsp", json.dumps(result).lower())
        self.assertNotIn("secret", json.dumps(result).lower())

    def test_privacy_and_child_scope_fail_closed_before_snapshot(self):
        repository = _DeviceRepository(
            [
                {"family_id": "fam_private", "device_id": "dev_1"},
                {"family_id": "fam_none", "device_id": "dev_2"},
                {"family_id": "fam_many", "device_id": "dev_3"},
            ]
        )
        profile = _ProfileRepository(
            children={
                "fam_private": [{"id": "child_1"}],
                "fam_none": [],
                "fam_many": [{"id": "child_2"}, {"id": "child_3"}],
            },
            privacy={
                "fam_private": {
                    "cameraCollectionAuthorized": True,
                    "childPrivacyAuthorized": False,
                },
                "fam_none": _authorized_privacy(),
                "fam_many": _authorized_privacy(),
            },
        )
        resolver = _RuntimeResolver()
        adapter = _service(
            repository=repository,
            profile=profile,
            resolver=resolver,
            observe=_ObserveService(),
        )

        result = adapter.run_observe_tick(
            window_start_ms=1_000,
            window_end_ms=2_000,
        )

        self.assertTrue(result["skipped"])
        self.assertEqual(resolver.calls, [])
        self.assertEqual(result["skip_reasons"]["privacy_not_authorized"], 1)
        self.assertEqual(result["skip_reasons"]["no_child"], 1)
        self.assertEqual(result["skip_reasons"]["child_scope_ambiguous"], 1)

    def test_cursor_wraps_without_starving_later_devices(self):
        repository = _DeviceRepository(
            [
                {"family_id": "fam_1", "device_id": "dev_1"},
                {"family_id": "fam_1", "device_id": "dev_2"},
            ]
        )
        profile = _ProfileRepository(
            children={"fam_1": [{"id": "child_1"}]},
            privacy={"fam_1": _authorized_privacy()},
        )
        resolver = _RuntimeResolver()
        adapter = _service(
            repository=repository,
            profile=profile,
            resolver=resolver,
            observe=_ObserveService(),
            max_devices=1,
        )

        for index in range(3):
            adapter.run_observe_tick(
                window_start_ms=index * 1_000,
                window_end_ms=(index + 1) * 1_000,
            )

        self.assertEqual(
            resolver.calls,
            [
                ("fam_1", "dev_1"),
                ("fam_1", "dev_2"),
                ("fam_1", "dev_1"),
            ],
        )

    def test_worker_aggregates_multi_device_result(self):
        class _Adapter:
            config = BoundCameraObservationConfig(interval_seconds=5)

            def run_observe_tick(self, **_kwargs):
                return {
                    "observation_count": 2,
                    "posted_count": 1,
                    "responses": [{"ok": True}],
                    "skipped": False,
                }

        result = CameraObservationWorker(_Adapter()).run_once(
            window_start_ms=1_000,
            window_end_ms=2_000,
        )
        self.assertEqual(result.observation_count, 2)
        self.assertEqual(result.posted_count, 1)
        self.assertEqual(result.responses, [{"ok": True}])

    def test_runtime_state_never_persists_reconstructable_frame_thumbnail(self):
        repository = _RuntimeStateRepository()
        store = ObservationRuntimeStateStore(repository)
        store.save(
            object(),
            family_id="fam_1",
            child_id="child_1",
            device_id="dev_1",
            payload={
                "prefilter": {
                    "last_frame_thumb_b64": "sensitive-frame",
                    "motion_score": 0.5,
                }
            },
            now=1_000,
        )

        stored = json.loads(repository.raw_detail_json)
        self.assertEqual(stored["prefilter"]["last_frame_thumb_b64"], "")
        self.assertEqual(stored["prefilter"]["motion_score"], 0.5)


def _service(
    *,
    repository,
    profile,
    resolver,
    observe,
    max_devices: int = 8,
):
    return BoundCameraObservationService(
        BoundCameraObservationConfig(
            interval_seconds=5,
            max_devices_per_tick=max_devices,
            offline_backoff_seconds=30,
            offline_backoff_max_seconds=300,
        ),
        device_repository=repository,
        profile_repository=profile,
        runtime_resolver=resolver,
        observe_service=observe,
        monotonic=lambda: 100.0,
    )


class _DeviceRepository:
    def __init__(self, rows):
        self.rows = sorted(rows, key=lambda row: (row["family_id"], row["device_id"]))

    @contextmanager
    def transaction(self):
        yield object()

    def list_active_observation_devices(
        self,
        _conn,
        *,
        after_family_id=None,
        after_device_id=None,
        limit=8,
    ):
        rows = self.rows
        if after_family_id and after_device_id:
            cursor = (after_family_id, after_device_id)
            rows = [
                row
                for row in rows
                if (row["family_id"], row["device_id"]) > cursor
            ]
        return rows[:limit]


class _ProfileRepository:
    def __init__(self, *, children, privacy, rules=None):
        self.children = children
        self.privacy = privacy
        self.rules = rules or {}

    @contextmanager
    def transaction(self):
        yield object()

    def get_setting(self, _conn, *, family_id, key):
        value = (
            self.privacy.get(family_id, {})
            if key == "privacy"
            else self.rules.get(family_id, {"taskObservationEnabled": True})
        )
        return {"value": json.dumps(value)}

    def list_children(self, _conn, *, family_id):
        return list(self.children.get(family_id, []))


class _RuntimeResolver:
    def __init__(self, failing_devices=None):
        self.failing_devices = set(failing_devices or [])
        self.calls = []

    def resolve(self, *, family_id, device_id, require_device):
        self.calls.append((family_id, device_id))
        if device_id in self.failing_devices:
            bridge = _Bridge(fails=True)
        else:
            bridge = _Bridge()
        return SimpleNamespace(bridge=bridge)


class _Bridge:
    def __init__(self, *, fails=False):
        self.fails = fails

    def fetch_snapshot(self):
        if self.fails:
            raise RuntimeError("camera IP and password must not leak")
        return CameraSnapshot(body=b"image", content_type="image/png")


class _ObserveService:
    def __init__(self):
        self.calls = []

    def run_tick(self, **kwargs):
        self.calls.append(kwargs)
        return ObserveTickResult(
            skipped=False,
            skip_reason="",
            analysis={"has_person": True},
            posted=True,
            observation_count=1,
            response={"ok": True},
        )


class _RuntimeStateRepository:
    def __init__(self):
        self.raw_detail_json = ""

    def get_current_behavior_state(self, *_args, **_kwargs):
        return None

    def upsert_behavior_state(self, *_args, **kwargs):
        self.raw_detail_json = kwargs["raw_detail_json"]


def _authorized_privacy():
    return {
        "cameraCollectionAuthorized": True,
        "childPrivacyAuthorized": True,
    }


if __name__ == "__main__":
    unittest.main()
