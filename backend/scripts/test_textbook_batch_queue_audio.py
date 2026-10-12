"""Local structural admission and existing durable-audio protocol mocks."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scripts.test_textbook_batch_queue as fixture
from content.teacher_profiles import get_formal_runtime_teacher_contract
from content.textbook_catalog import canonical, digest
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError
from services.textbook_batch_audio import _external_once, build_audio_plan
from services.textbook_batch_generation_service import atomic_json
from services.textbook_batch_queue_audio_service import TextbookBatchQueueAudioService, structural_review, _Markup


class PictureStructureTest(unittest.TestCase):
    def signature(self, content):
        markup = _Markup('<button data-mira-picture-choice="picture">' + content + '</button>')
        self.assertEqual(len(markup.choices), 1)
        return digest(markup.choices[0])

    def test_actual_svg_ancestor_positions_are_part_of_picture_identity(self):
        def birds(chick, duck):
            return ('<svg viewBox="0 0 640 400"><g transform="translate'+chick+'">'
                    '<circle r="20" fill="yellow"/></g><g transform="translate'+duck+'">'
                    '<ellipse rx="30" ry="15" fill="white"/></g></svg>')
        ahead = self.signature(birds('(390 230)', '(220 230)'))
        behind = self.signature(birds('(220 230)', '(390 230)'))
        beside = self.signature(birds('(315 150)', '(315 310)'))
        self.assertEqual(len({ahead, behind, beside}), 3)

    def test_equivalent_transforms_and_labels_cannot_fake_distinct_graphics(self):
        plain = '<svg><rect width="20" height="10"/></svg>'
        decorated = '<svg><g id="different" aria-label="another picture" transform="translate(0,0) rotate(360)"><rect width="20" height="10"/></g><g transform="translate(99 99)"></g></svg>'
        self.assertEqual(self.signature(plain), self.signature(decorated))
        positioned = '<svg><g transform="translate(10 20)"><rect width="20" height="10"/></g></svg>'
        equivalent = '<svg><g transform="translate(5,10)"><g transform="scale(1) matrix(1 0 0 1 5 10)"><rect width="20" height="10"/></g></g></svg>'
        self.assertEqual(self.signature(positioned), self.signature(equivalent))
        self.assertNotEqual(self.signature(plain), self.signature(positioned))

    def test_group_scope_ends_before_sibling_and_empty_groups_are_not_shapes(self):
        grouped = '<svg><g transform="translate(10 20)"><circle r="10"/></g><rect width="20" height="10"/></svg>'
        markup = _Markup('<button data-mira-picture-choice="a">'+grouped+'</button>')
        shapes = dict((tag, attrs) for tag, attrs in markup.choices[0])
        self.assertIn('svgAncestorTransform', shapes['circle'])
        self.assertNotIn('svgAncestorTransform', shapes['rect'])
        empty = _Markup('<button data-mira-picture-choice="a"><svg><g transform="translate(5 8)"></g></svg></button>')
        self.assertFalse(any(tag in {'path', 'rect', 'circle', 'ellipse', 'img'} for tag, _ in empty.choices[0]))
        with self.assertRaisesRegex(ValueError, 'picture_svg_transform_invalid'):
            self.signature('<svg><g transform="translate(1 nope)"><circle r="10"/></g></svg>')


class QueueAudioTest(unittest.TestCase):
    def setUp(self):
        isolated = fixture.QueueTest("test_queue_lock_prevents_parallel_operator")
        isolated.setUp()
        self.addCleanup(isolated.doCleanups)
        self.queue, self.root, self.runtime = isolated.queue, isolated.root, isolated.runtime
        self.task = isolated.eligible[0]
        index = isolated.index([self.task])
        entry = json.loads(index.read_text())["entries"][0]
        design_path = Path(entry["designPlanPath"])
        design = json.loads(design_path.read_text())
        design.update(sceneCount=2, finiteCues=[{"cueId": "welcome", "teacherText": "看一看。"},
                                               {"cueId": "done", "teacherText": "再观察一下。"}])
        design_path.write_text(canonical(design))
        self.queue.admit_index(index)
        self.queue.prepare(limit=1)
        self.folder = self.queue.drafts / self.task["taskId"]
        self.frozen = json.loads((self.folder / "input.json").read_text())
        teacher = self.frozen["runtimeBatchContext"]["teacher"]
        voice = get_formal_runtime_teacher_contract("math")["runtime"]["voiceConfig"]
        cues = '<script type="application/json" id="mira-narration-cues">' + json.dumps({
            "schemaVersion": "mira.interactive.narration-cues.v1", "cues": [
                {"id": "welcome", "text": "看一看。"}, {"id": "done", "text": "再观察一下。"}]}, ensure_ascii=False) + '</script>'
        code = """window.addEventListener('message',e=>{if(e.source!==parent)return;
if(e.data.type==='SET_WIDGET_STATE'){}if(e.data.type==='HIGHLIGHT_ELEMENT'){} });
function begin(){window.miraNarrate('welcome');}
function finish(){window.miraNarrate('done');}"""
        common = '<html><head><meta name="mira-responsive-activity" content="low-reading-v1"></head><body>'
        choices = '<button data-mira-picture-choice="a"><svg><rect width="20" height="10"/></svg></button><button data-mira-picture-choice="b"><svg><circle r="10"/></svg></button>'
        self.classroom = {"id": "synthetic-local-classroom", "stage": {"id": "synthetic-local-classroom",
            "generatedAgentConfigs": [{"role": "teacher", "name": teacher["teacherName"],
                "avatar": teacher["avatarPath"], "teacherProfile": teacher["teacherProfile"], "voiceConfig": voice}]},
            "scenes": [{"id": "pictures", "type": "interactive", "actions": [], "content": {
                "type": "interactive", "widgetType": "game", "html": common + choices + cues + '<script>' + code + '</script></body></html>'}},
                {"id": "model", "type": "interactive", "actions": [], "content": {
                    "type": "interactive", "widgetType": "visualization3d", "html": common + '<canvas></canvas>' + cues + '<script>' + code +
                    'function renderFixture(){const renderer=new THREE.WebGLRenderer();const g=new THREE.BoxGeometry();const m=new THREE.Mesh(g);renderer.render(m);requestAnimationFrame(renderFixture);}' +
                    '</script></body></html>'}}]}
        self.save_classroom()
        self.media_root = self.root / "runtime-classrooms"
        self.media_root.mkdir()
        self.audio = TextbookBatchQueueAudioService(self.queue, classroom_directory=self.media_root)

    def save_classroom(self):
        atomic_json(self.folder / "classroom.json", self.classroom)
        state = json.loads((self.folder / "state.json").read_text())
        state.update(status="generated_needs_review", classroomId=self.classroom["id"],
            classroomSha256=digest(self.classroom), runtimeOrigin=self.runtime.base_url)
        atomic_json(self.folder / "state.json", state)

    def complete_audit(self):
        plan = build_audio_plan(self.classroom, self.frozen["binding"], self.runtime.base_url)
        result = {"planSha256": digest(plan), "allSegmentsPassed": True,
            "expectedSegments": len(plan["workload"]), "completedSegments": len(plan["workload"]),
            "segments": [{"similarityBps": 10000} for _ in plan["workload"]]}
        result["sha256"] = digest(result)
        return result

    def successful_narration(self, _runtime, _classroom, _binding, output, *_args, **_kwargs):
        output.mkdir(exist_ok=True)
        result = self.complete_audit()
        atomic_json(output / "audit.json", result)
        return result

    def test_actual_local_structural_check_then_serial_narrator_and_separate_summary(self):
        review = structural_review(self.folder, self.media_root)
        self.assertEqual(review["issues"], [])
        self.assertFalse(review["browserQAPassed"])
        with patch("services.textbook_batch_queue_audio_service.narrate_candidate", side_effect=self.successful_narration) as narrate:
            state = self.audio.narrate()[0]
            self.assertEqual(state["status"], "audio_completed_needs_review")
            self.assertFalse(state["previewReady"])
            self.assertFalse(state["publicationAllowed"])
            self.assertEqual(self.audio.narrate(), [])
            narrate.assert_called_once()
        summary = self.queue.status()
        self.assertEqual(summary["generatedDraftCount"], 1)
        self.assertEqual(summary["audioCompletedDraftCount"], 1)
        self.assertEqual(summary["previewReadyCount"], 0)
        self.assertEqual(summary["browserVerifiedCount"], 0)

    def test_dynamic_cue_and_syntax_block_all_audio_calls(self):
        source = self.classroom["scenes"][0]["content"]["html"]
        self.classroom["scenes"][0]["content"]["html"] = source.replace("window.miraNarrate('welcome')", "window.miraNarrate(currentCue)")
        self.save_classroom()
        with patch("services.textbook_batch_queue_audio_service.narrate_candidate") as narrate:
            result = self.audio.narrate()[0]
            self.assertEqual(result["status"], "audio_blocked")
            self.assertTrue(any("fixed_declared_literals" in issue for issue in result["issues"]))
            narrate.assert_not_called()

    def test_native_renderer_missing_content_type_blocks_audio_before_provider(self):
        self.classroom["scenes"][0]["content"].pop("type")
        self.save_classroom()
        with patch("services.textbook_batch_queue_audio_service.narrate_candidate") as narrate:
            result = self.audio.narrate()[0]
            self.assertIn("pictures:native_interactive_content_type_required", result["issues"])
            narrate.assert_not_called()

    def test_emoji_and_same_picture_different_label_do_not_pass(self):
        source = self.classroom["scenes"][0]["content"]["html"]
        source = source.replace('<circle r="10"/>', '<rect width="20" height="10"/>')
        source = source.replace('</body>', '<p>🙂</p></body>')
        self.classroom["scenes"][0]["content"]["html"] = source
        self.save_classroom()
        review = structural_review(self.folder, self.media_root)
        self.assertIn("emoji_in_scene_source", review["issues"])
        self.assertIn("pictures:distinct_meaningful_picture_container_structure_missing", review["issues"])
        self.runtime.start_formal_audio_tts.assert_not_called()

    def test_group_position_pictures_pass_without_lowering_picture_count_or_duplicate_guard(self):
        source = self.classroom["scenes"][0]["content"]["html"]
        source = source.replace('<svg><rect width="20" height="10"/></svg>',
            '<svg><g transform="translate(15 0)"><rect width="20" height="10"/></g></svg>')
        source = source.replace('<svg><circle r="10"/></svg>',
            '<svg><g transform="translate(0 15)"><rect width="20" height="10"/></g></svg>')
        self.classroom["scenes"][0]["content"]["html"] = source
        self.save_classroom()
        self.assertEqual(structural_review(self.folder, self.media_root)['issues'], [])
        self.classroom["scenes"][0]["content"]["html"] = source.replace('translate(0 15)', 'translate(15 0)')
        self.save_classroom()
        self.assertIn('pictures:distinct_meaningful_picture_container_structure_missing',
                      structural_review(self.folder, self.media_root)['issues'])

    def test_canvas_label_without_renderer_is_rejected_before_audio(self):
        self.classroom["scenes"][1]["content"]["html"] = self.classroom["scenes"][1]["content"]["html"].replace(
            'new THREE.WebGLRenderer()', 'fakeRenderer()')
        self.save_classroom()
        with patch("services.textbook_batch_queue_audio_service.narrate_candidate") as narrate:
            result = self.audio.narrate()[0]
            self.assertTrue(any("renderer_mesh_geometry" in issue for issue in result["issues"]))
            narrate.assert_not_called()

    def native_webgl_source(self):
        return """function meshFixture(){const gl=document.querySelector('canvas').getContext('webgl2');
const shader=gl.createShader(gl.VERTEX_SHADER);gl.shaderSource(shader,'attribute vec3 position;uniform mat4 mvp;void main(){gl_Position=mvp*vec4(position,1.0);}');gl.compileShader(shader);
const program=gl.createProgram();gl.linkProgram(program);const buffer=gl.createBuffer();
gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([0,0,0,1,0,0,0,1,1]),gl.STATIC_DRAW);
gl.uniformMatrix4fv(0,false,new Float32Array(16));gl.drawArrays(gl.TRIANGLES,0,3);requestAnimationFrame(meshFixture);}"""

    def replace_three_with(self, source):
        content = self.classroom["scenes"][1]["content"]
        content["html"] = content["html"].replace(
            'function renderFixture(){const renderer=new THREE.WebGLRenderer();const g=new THREE.BoxGeometry();const m=new THREE.Mesh(g);renderer.render(m);requestAnimationFrame(renderFixture);}', source)
        self.save_classroom()

    def test_native_webgl_shader_vertex_buffer_matrix_path_is_supported(self):
        self.replace_three_with(self.native_webgl_source())
        review = structural_review(self.folder, self.media_root)
        self.assertEqual(review["issues"], [])
        self.assertEqual(review["scenes"][1]["rendererStructure"], "native_webgl_mesh")
        self.assertFalse(review["browserQAPassed"])

    def test_canvas2d_rotation_does_not_masquerade_as_3d(self):
        self.replace_three_with("function rotatePicture(){const ctx=document.querySelector('canvas').getContext('2d');ctx.rotate(0.5);ctx.fillRect(0,0,30,30);requestAnimationFrame(rotatePicture);}")
        review = structural_review(self.folder, self.media_root)
        self.assertIn("model:actual_3d_renderer_mesh_geometry_loop_structure_missing", review["issues"])

    def test_native_webgl_without_matrix_transform_is_blocked(self):
        self.replace_three_with(self.native_webgl_source().replace('gl.uniformMatrix4fv', 'fakeMatrix'))
        review = structural_review(self.folder, self.media_root)
        self.assertIn("model:actual_3d_renderer_mesh_geometry_loop_structure_missing", review["issues"])

    def test_designed_video_missing_cannot_be_covered_by_correct_cues(self):
        # Re-freeze a synthetic local test input only; production snapshots are
        # immutable and the same hash change would fail the saved state binding.
        self.frozen["activityDesign"]["scenes"] = [{"sceneId": "expected_video", "type": "interactive",
            "widgetType": "game", "startCueId": "welcome"}]
        self.frozen["activityDesignSha256"] = digest(self.frozen["activityDesign"])
        self.frozen["inputSha256"] = digest({key: value for key, value in self.frozen.items() if key != "inputSha256"})
        atomic_json(self.folder / "input.json", self.frozen)
        state = json.loads((self.folder / "state.json").read_text())
        state["inputSha256"] = self.frozen["inputSha256"]
        atomic_json(self.folder / "state.json", state)
        # A unique actual scene has the exact intended cue and widget; the
        # missing video itself must still block charging for narration.
        model = self.classroom["scenes"][1]["content"]
        model["html"] = model["html"].replace('{"id": "welcome", "text": "看一看。"}, ', '').replace(
            "window.miraNarrate('welcome');", '')
        self.save_classroom()
        with patch("services.textbook_batch_queue_audio_service.narrate_candidate") as narrate:
            result = self.audio.narrate()[0]
            self.assertIn("design_actual_video_scene_missing:expected_video", result["issues"])
            narrate.assert_not_called()

    def required_video_fixture(self, required_src, *, actual_src=True):
        # Synthetic container bytes only test local source validation, never
        # playback or the semantics of a generated teaching video.
        source = f'/api/classroom-media/{self.classroom["id"]}/media/observation.mp4'
        media = self.media_root / self.classroom["id"] / "media" / "observation.mp4"
        media.parent.mkdir(parents=True, exist_ok=True)
        def box(kind, payload=b""):
            return (len(payload) + 8).to_bytes(4, "big") + kind + payload
        media.write_bytes(box(b"ftyp", b"isom" + b"\0" * 4 + b"isom")
                         + box(b"moov") + box(b"mdat", b"fixture"))
        planned = {"sceneId": "observe_ten", "type": "interactive",
                   "widgetType": "game", "startCueId": "welcome"}
        if required_src is not None:
            planned["requiredVideoElement"] = {"src": source if required_src is True else required_src}
        self.frozen["activityDesign"]["scenes"] = [planned]
        self.frozen["activityDesignSha256"] = digest(self.frozen["activityDesign"])
        self.frozen["inputSha256"] = digest({key: value for key, value in self.frozen.items()
                                             if key != "inputSha256"})
        atomic_json(self.folder / "input.json", self.frozen)
        state = json.loads((self.folder / "state.json").read_text())
        state["inputSha256"] = self.frozen["inputSha256"]
        atomic_json(self.folder / "state.json", state)
        model = self.classroom["scenes"][1]["content"]
        model["html"] = model["html"].replace('{"id": "welcome", "text": "看一看。"}, ', '').replace(
            "window.miraNarrate('welcome');", '')
        if actual_src:
            content = self.classroom["scenes"][0]["content"]
            content["html"] = content["html"].replace("</body>",
                f'<video controls playsinline src="{source}"></video></body>')
        self.save_classroom()
        return media

    def test_required_video_element_exact_real_source_recognized_without_scene_name_hint(self):
        self.required_video_fixture(True)
        review = structural_review(self.folder, self.media_root)
        self.assertEqual(review["issues"], [])
        self.assertEqual(review["scenes"][0]["videoSources"], [
            f'/api/classroom-media/{self.classroom["id"]}/media/observation.mp4'])
        self.assertFalse(review["browserQAPassed"])

    def test_empty_required_source_does_not_exempt_independent_game(self):
        self.required_video_fixture("")
        review = structural_review(self.folder, self.media_root)
        self.assertIn("design_independent_game_or_route_replaced_with_video:observe_ten", review["issues"])

    def test_unplanned_video_does_not_replace_an_independent_game(self):
        self.required_video_fixture(None)
        review = structural_review(self.folder, self.media_root)
        self.assertIn("design_independent_game_or_route_replaced_with_video:observe_ten", review["issues"])

    def test_required_video_must_exactly_match_real_element_source(self):
        self.required_video_fixture(f'/api/classroom-media/{self.classroom["id"]}/media/other.mp4')
        review = structural_review(self.folder, self.media_root)
        self.assertIn("design_required_video_source_not_exactly_present:observe_ten", review["issues"])

    def test_required_video_source_does_not_bypass_missing_bytes(self):
        self.required_video_fixture(True).unlink()
        review = structural_review(self.folder, self.media_root)
        self.assertIn("pictures:actual_video_bytes_missing_or_unsafe", review["issues"])

    def test_required_video_source_without_video_element_is_blocked(self):
        self.required_video_fixture(True, actual_src=False)
        review = structural_review(self.folder, self.media_root)
        self.assertIn("design_actual_video_scene_missing:observe_ten", review["issues"])
        self.assertIn("design_required_video_source_not_exactly_present:observe_ten", review["issues"])

    def test_placeholder_required_source_is_not_a_video_role(self):
        self.required_video_fixture("gen_vid_observe_ten")
        review = structural_review(self.folder, self.media_root)
        self.assertIn("design_required_video_source_invalid:observe_ten", review["issues"])
        self.assertIn("design_independent_game_or_route_replaced_with_video:observe_ten", review["issues"])

    def test_invalid_javascript_is_a_per_task_structural_block(self):
        self.classroom["scenes"][0]["content"]["html"] = self.classroom["scenes"][0]["content"]["html"].replace(
            'function begin(){', 'function begin( {')
        self.save_classroom()
        with patch("services.textbook_batch_queue_audio_service.narrate_candidate") as narrate:
            result = self.audio.narrate()[0]
            self.assertIn("pictures:javascript_syntax_invalid", result["issues"])
            narrate.assert_not_called()

    def test_missing_saved_audit_cannot_be_counted_as_audio_complete(self):
        with patch("services.textbook_batch_queue_audio_service.narrate_candidate", return_value=self.complete_audit()):
            self.assertEqual(self.audio.narrate()[0]["status"], "audio_blocked")
        self.assertEqual(self.queue.status()["audioCompletedDraftCount"], 0)

    def test_audio_lock_is_serial_and_independent_of_generation_lock(self):
        with self.audio._lock():
            self.assertEqual(self.queue.status()["generatedDraftCount"], 1)
            with self.assertRaisesRegex(ValueError, "audio_operator_already_running"):
                TextbookBatchQueueAudioService(self.queue).narrate()

    def test_teacher_change_is_rejected_before_narrator(self):
        self.classroom["stage"]["generatedAgentConfigs"][0]["name"] = "Unknown teacher"
        self.save_classroom()
        with patch("services.textbook_batch_queue_audio_service.narrate_candidate") as narrate:
            self.assertEqual(self.audio.narrate()[0]["status"], "audio_blocked")
            narrate.assert_not_called()

    def test_unknown_get404_never_reposts_and_new_segments_need_explicit_continue(self):
        output = self.folder / "audio-audit"
        def no_receipt(_identity):
            raise OpenMaicFullRuntimeError("missing", "synthetic", status_code=404)
        self.runtime.get_formal_audio_tts.side_effect = no_receipt
        self.runtime.start_formal_audio_tts.side_effect = TimeoutError()
        def attempt(runtime, _classroom, _binding, directory, *_args, **_kwargs):
            directory.mkdir(exist_ok=True)
            _external_once(runtime, directory / "tbbtts_known.json", "tbbtts_known", "tts",
                           {"request_id": "tbbtts_known"})
            _external_once(runtime, directory / "tbbtts_next.json", "tbbtts_next", "tts",
                           {"request_id": "tbbtts_next"})
            return self.successful_narration(runtime, _classroom, _binding, directory)
        with patch("services.textbook_batch_queue_audio_service.narrate_candidate", side_effect=attempt):
            self.assertEqual(self.audio.narrate()[0]["status"], "audio_unknown_needs_reconciliation")
            self.assertEqual(self.audio.narrate()[0]["status"], "audio_unknown_needs_reconciliation")
            self.assertEqual(self.runtime.start_formal_audio_tts.call_count, 1)
            self.runtime.get_formal_audio_tts.side_effect = lambda identity: (
                {"requestId": identity, "status": "succeeded"} if identity == "tbbtts_known" else no_receipt(identity))
            self.assertEqual(self.audio.narrate()[0]["status"], "audio_waiting_explicit_continue")
            self.assertFalse((output / "tbbtts_next.json").exists())
            self.assertEqual(self.runtime.start_formal_audio_tts.call_count, 1)
            self.runtime.start_formal_audio_tts.side_effect = lambda **payload: {"requestId": payload["request_id"], "status": "succeeded"}
            self.assertEqual(self.audio.narrate(continue_audio=True)[0]["status"], "audio_completed_needs_review")
            self.assertEqual(self.runtime.start_formal_audio_tts.call_count, 2)
            self.assertEqual(self.runtime.start_formal_audio_tts.call_args.kwargs["request_id"], "tbbtts_next")

    def test_known_low_asr_stays_blocked_without_automatic_reconciliation(self):
        with patch("services.textbook_batch_queue_audio_service.narrate_candidate",
                   side_effect=RuntimeError("narration_asr_semantic_review_required_no_retry")) as narrate:
            self.assertEqual(self.audio.narrate()[0]["status"], "audio_blocked")
            self.assertEqual(self.audio.narrate(continue_audio=True), [])
            narrate.assert_called_once()

    def test_existing_authorization_state_drift_fails_before_any_audio_call(self):
        with patch("services.textbook_batch_queue_audio_service.narrate_candidate", side_effect=TimeoutError()):
            self.audio.narrate()
        state_path = self.folder / "audio-state.json"
        value = json.loads(state_path.read_text())
        value["bound"]["planSha256"] = "0" * 64
        atomic_json(state_path, value)
        with patch("services.textbook_batch_queue_audio_service.narrate_candidate") as narrate:
            with self.assertRaisesRegex(ValueError, "frozen_state_changed"):
                self.audio.narrate()
            narrate.assert_not_called()

    def test_existing_frozen_inheritance_is_passed_to_original_narrator(self):
        # Only wiring is mocked here; real inheritance receipt validation remains
        # the existing narrate_candidate/_inheritance_set_targets implementation.
        inheritance = {"schemaVersion": "synthetic-test-only"}
        output = self.folder / "audio-audit"
        output.mkdir()
        atomic_json(output / "inheritance-manifest.json", inheritance)
        with patch("services.textbook_batch_queue_audio_service.normalize_audio_inheritance", return_value=inheritance), patch(
                "services.textbook_batch_queue_audio_service.narrate_candidate", side_effect=self.successful_narration) as narrate:
            self.audio.narrate()
            self.assertEqual(narrate.call_args.kwargs["audio_inheritance"], inheritance)


if __name__ == "__main__":
    unittest.main()
