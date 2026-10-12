"""Finite authoring contract, immutable output and actual fixed JS regressions."""
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
import importlib.util
from unittest.mock import patch

from content.textbook_batch import build_plan
from content.textbook_batch_generation import freeze_input
from content.textbook_catalog import canonical, digest
from content.textbook_activity_ir import build_ir, byte_sha, safe_svg
from services.textbook_activity_compiler import (compile_batch, preflight, render, game_scene,
                                                model_scene, route_scene)

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "openmaic-runtime/.runtime/OpenMAIC/node_modules/linkedom/worker.js"


class DeterministicActivityCompiler(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get("MIRA_TASK_TMPDIR"))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        catalog = self.root / "catalog"
        catalog.mkdir()
        source = ROOT / "backend/content/textbooks/official-directories-v1/bnu-math-g1-lower-2022-standard.directory-c4be26f1b4e105927cc4b5a0.json"
        (catalog / "source.json").write_bytes(source.read_bytes())
        _, tasks = build_plan(catalog, superseded_ids=set())
        task = next(t for t in tasks if t["kind"] == "book_exploration")
        self.frozen = freeze_input(task)
        receipt = self.root / "video-receipt.json"
        receipt.write_text(json.dumps({"probe": {"durationMs": 12000}}))
        self.media = [{"src": "/api/classroom-media/tbmedia_fixture/media/exact.mp4", "receiptPath": str(receipt)}]
        self.media_guard = patch("content.textbook_activity_ir.validate_frozen_provided_media", return_value=self.media)
        self.media_guard.start()
        self.addCleanup(self.media_guard.stop)
        assets = []
        for i, key in enumerate(("one", "three", "five")):
            svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 128" aria-label="' + key + '"><rect x="1" y="1" width="158" height="126" fill="#faf7ee"/>'
            svg += ''.join(f'<circle cx="{20 + n * 23}" cy="64" r="9" fill="#779d91"/>' for n in range(2 * i + 1)) + '</svg>'
            assets.append({"assetId": key, "sha256": byte_sha(svg.encode()), "svgMarkup": svg})
        def scene(key, fields, widget="game"):
            refs = list(dict.fromkeys(fields))
            return {"sceneId": key, "type": "interactive", "widgetType": widget, "title": key,
                    "finiteCues": [{"cueId": key + "_" + c, "teacherText": "请仔细观察这幅图。"} for c in refs]}
        video = scene("video", ["intro", "replay", "finish", "one", "three", "five"])
        video.update(initialCueId="video_intro", replayCueId="video_replay", finishCueId="video_finish",
                     requiredVideoElement={"src": self.media[0]["src"]},
                     observations=[{"assetId": key, "cueId": "video_" + key, "seekSeconds": .5 + i * 4} for i, key in enumerate(("one", "three", "five"))])
        game = scene("game", ["intro", "reset", "retry", "hint", "complete", "ask0", "yes0", "ask1", "yes1", "ask2", "yes2"])
        game.update(initialCueId="game_intro", resetCueId="game_reset", retryCueId="game_retry", hintCueId="game_hint", completeCueId="game_complete",
                    rounds=[{"roundId": "round" + str(i), "mode": "visible_picture_matching", "targetAssetId": key,
                             "optionAssetIds": ["one", "three", "five"][i:] + ["one", "three", "five"][:i],
                             "instructionCueId": "game_ask" + str(i), "matchCueId": "game_yes" + str(i)} for i, key in enumerate(("one", "three", "five"))])
        model = scene("model", ["intro", "reset", "retry", "complete", "one", "three", "five"], "visualization3d")
        model.update(modelAdapterKey="abacus_five_independent_beads", initialCueId="model_intro", resetCueId="model_reset",
                     retryCueId="model_retry", completeCueId="model_complete", states=[{"sceneStateId": k, "assetId": k,
                       "observationCueId": "model_" + k} for k in ("one", "three", "five")])
        units = self.frozen["directoryScope"]
        route = scene("route", ["intro", "finish"] + ["unit" + str(i) for i in range(len(units))])
        route.update(initialCueId="route_intro", finishCueId="route_finish", entries=[{
            "unitId": u["unitId"], "title": u["title"], "representativeNodeId": u["lessons"][0]["nodeId"],
            "representativeNodeTitle": u["lessons"][0]["title"], "assetId": ("one", "three", "five")[i % 3],
            "routeCueId": "route_unit" + str(i)} for i, u in enumerate(units)])
        self.design = {"schemaVersion": "mira.textbook.activity-design.v1", "status": "draft", "publicationAllowed": False,
                       "kind": "book_exploration", "binding": self.frozen["binding"], "manifestSha256": self.frozen["manifestSha256"],
                       "title": "原创图片预习", "assetPlan": assets, "scenes": [video, game, model, route]}
        self.design["finiteCues"] = [c for s in self.design["scenes"] for c in s["finiteCues"]]
        self.freeze()

    def freeze(self):
        self.frozen["activityDesign"] = deepcopy(self.design)
        self.frozen["activityDesignSha256"] = digest(self.design)
        self.frozen["inputSha256"] = digest({k: v for k, v in self.frozen.items() if k != "inputSha256"})
        source = self.root / "source"
        source.mkdir(exist_ok=True)
        (source / "input.json").write_text(canonical(self.frozen) + "\n")
        (source / "design.json").write_text(canonical(self.design) + "\n")
        (source / "state.json").write_text(canonical({"schemaVersion": "mira.textbook.private-batch-generation-state.v1",
            "taskId": self.frozen["taskId"], "inputSha256": self.frozen["inputSha256"],
            "status": "dispatch_unknown", "runtimeJobId": "original-unknown", "publicationAllowed": False,
            "studentDeliveryAllowed": False, "createdAt": 1700000000000}) + "\n")
        self.entry = {"inputPath": str(source / "input.json"), "inputSha256": self.frozen["inputSha256"],
            "designPath": str(source / "design.json"), "activityDesignSha256": self.frozen["activityDesignSha256"],
            "sourceScopeSha256": digest(self.frozen["directoryScope"]), "providedMediaSha256": digest(self.media)}

    def ir(self):
        return preflight(self.entry)[3]

    def test_exact_contract_rejects_changed_scope_teacher_picture_media_and_foreign_cue(self):
        self.assertEqual(self.ir()["modelAdapterKey"], "abacus_five_independent_beads")
        for field in ("inputSha256", "activityDesignSha256", "sourceScopeSha256", "providedMediaSha256"):
            entry = {**self.entry, field: "0" * 64}
            with self.subTest(field=field), self.assertRaises(ValueError):
                preflight(entry)
        self.design["scenes"][1]["rounds"][0]["matchCueId"] = "model_one"
        self.freeze()
        with self.assertRaisesRegex(ValueError, "foreign_scene_cue"):
            self.ir()

    def test_unknown_family_wrong_grade_and_lesson_are_unsupported_not_cubes(self):
        for key, code in (("generic_cube", "unsupported_semantic"), ("lever_beam_same_fulcrum", "subject_or_grade")):
            self.design["scenes"][2]["modelAdapterKey"] = key
            self.freeze()
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, code):
                self.ir()
        self.frozen["kind"] = "lesson_courseware"
        self.frozen["inputSha256"] = digest({k: v for k, v in self.frozen.items() if k != "inputSha256"})
        with self.assertRaisesRegex(ValueError, "unsupported_lesson"):
            build_ir(self.frozen, self.design, expected_input_sha=self.frozen["inputSha256"],
                expected_design_sha=digest(self.design), expected_scope_sha=self.entry["sourceScopeSha256"], expected_media_sha=digest(self.media))

    def test_svg_active_content_and_hash_drift_rejected(self):
        svg = self.design["assetPlan"][0]["svgMarkup"]
        for replacement in ('<script>alert(1)</script>', '<foreignObject/>', '<image href="https://outside/x.png"/>', '<path onclick="x()"/>'):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                safe_svg(svg.replace('</svg>', replacement + '</svg>'))
        self.design["assetPlan"][0]["svgMarkup"] = svg.replace('circle', 'ellipse')
        self.freeze()
        with self.assertRaisesRegex(ValueError, "picture_hash"):
            self.ir()

    def test_well_unit_guide_preserves_physical_states_and_rejects_foreign_cues(self):
        catalog = self.root / "chinese-catalog"
        catalog.mkdir()
        source = ROOT / "backend/content/textbooks/official-directories-v1/pep-chinese-g1-lower-2022-standard.directory-b30168cf88d5ee5709335698.json"
        (catalog / "source.json").write_bytes(source.read_bytes())
        _, tasks = build_plan(catalog, superseded_ids=set())
        task = next(t for t in tasks if t["kind"] == "unit_guide")
        self.frozen = freeze_input(task)
        self.design.update(kind="unit_guide", binding=self.frozen["binding"], manifestSha256=self.frozen["manifestSha256"])
        model = self.design["scenes"][2]
        model.update(modelAdapterKey="chinese_well_bucket_scene", adapterId="well_bucket_lift_v1",
                     lowerCueId="model_three", raiseCueId="model_five", states=[
                         {"sceneStateId": k, "observationCueId": cue}
                         for k, cue in zip(("high_empty", "low_full", "high_full"),
                                           ("model_intro", "model_three", "model_five"))])
        route = self.design["scenes"][3]
        route.pop("entries")
        route["nodes"] = [{**{k: n[k] for k in ("nodeId", "title", "sectionTitle")},
                            "assetId": "one", "routeCueId": "route_intro"}
                           for n in self.frozen["directoryScope"][0]["lessons"]]
        self.freeze()
        html = model_scene(self.ir()["scenes"][2], self.ir()["assets"])
        self.assertIn("animateBucket(.02", html)
        self.assertIn("animateBucket(1.5", html)
        self.assertIn("水井剖面模型", html)
        original = deepcopy(model)
        for mutate, error in (
            (lambda m: m.update(adapterId="arbitrary"), "well_guide_contract"),
            (lambda m: m.update(lowerCueId="video_intro"), "foreign_scene_cue"),
            (lambda m: m["states"][1].update(observationCueId="model_five"), "well_guide_contract"),
            (lambda m: m.update(geometry={}), "well_guide_contract"),
        ):
            self.design["scenes"][2] = deepcopy(original)
            mutate(self.design["scenes"][2])
            self.freeze()
            with self.assertRaisesRegex(ValueError, error):
                self.ir()

    def test_zongzi_guide_rejects_swapped_states_foreign_cues_and_injected_geometry(self):
        catalog = self.root / "food-catalog"
        catalog.mkdir()
        source = ROOT / "backend/content/textbooks/official-directories-v1/pep-chinese-g1-lower-2022-standard.directory-b30168cf88d5ee5709335698.json"
        (catalog / "source.json").write_bytes(source.read_bytes())
        _, tasks = build_plan(catalog, superseded_ids=set())
        self.frozen = freeze_input(next(t for t in tasks if t["kind"] == "unit_guide"))
        self.design.update(kind="unit_guide", binding=self.frozen["binding"], manifestSha256=self.frozen["manifestSha256"])
        model = self.design["scenes"][2]
        model.update(modelAdapterKey="chinese_zongzi_layers_scene", adapterId="zongzi_layers_v1",
                     openCueId="model_three", closeCueId="model_five", states=[
                         {"sceneStateId": k, "observationCueId": cue}
                         for k, cue in zip(("wrapped", "open", "rewrapped"),
                                           ("model_intro", "model_three", "model_five"))])
        route = self.design["scenes"][3]
        route.pop("entries")
        route["nodes"] = [{**{k: n[k] for k in ("nodeId", "title", "sectionTitle")},
                            "assetId": "one", "routeCueId": "route_intro"}
                           for n in self.frozen["directoryScope"][0]["lessons"]]
        self.freeze()
        self.assertEqual(self.ir()["modelAdapterKey"], "chinese_zongzi_layers_scene")
        original = deepcopy(model)
        for mutate, error in (
            (lambda m: m.update(adapterId="arbitrary"), "zongzi_guide_contract"),
            (lambda m: m.update(openCueId="video_intro"), "foreign_scene_cue"),
            (lambda m: m["states"][1].update(observationCueId="model_five"), "zongzi_guide_contract"),
            (lambda m: m.update(geometry={}), "zongzi_guide_contract"),
            (lambda m: m.update(script="untrusted"), "zongzi_guide_contract"),
        ):
            self.design["scenes"][2] = deepcopy(original)
            mutate(self.design["scenes"][2])
            self.freeze()
            with self.assertRaisesRegex(ValueError, error):
                self.ir()

    def test_protocol_examples_never_executed_and_typo_inventory_not_silently_repaired(self):
        self.design["scenes"][0]["copyableVideoMarkup"] = '<script>throw new Error("untrusted")</script>'
        self.design["scenes"][1]["copyableCueDispatchJavascript"] = 'window.miraNarrate(dynamic);'
        self.freeze()
        ir = self.ir()
        classroom = render(ir, self.frozen, "local-test", 1)
        text = canonical(classroom)
        self.assertNotIn("untrusted", text)
        self.assertNotIn("miraNarrate(dynamic)", text)
        self.assertTrue(all(s["type"] == s["content"]["type"] == "interactive" for s in classroom["scenes"]))
        self.design["scenes"][0]["cueInventoryJSON"] = json.dumps({"schemaVersion": "mira.interaction.narration-cues.v1", "cues": []})
        self.freeze()
        with self.assertRaisesRegex(ValueError, "inventory_mismatch"):
            self.ir()

    def test_create_only_resume_unknown_parent_and_all_batch_preflight_before_writes(self):
        evidence = {p: Path(p).read_bytes() for p in (self.entry["inputPath"], str(self.root / "source/state.json"))}
        target = self.root / "output"
        review = {"structuralChecksPassed": True, "issues": []}
        with patch("services.textbook_activity_compiler.OWNED", self.root), patch(
                "services.textbook_batch_queue_audio_service.structural_review", return_value=review):
            result = compile_batch([self.entry], target)
            self.assertEqual(compile_batch([self.entry], target), result)
            folder = Path(result[0]["candidateDirectory"])
            state = json.loads((folder / "state.json").read_text())
            self.assertEqual(state["sourceGenerationStatus"], "dispatch_unknown")
            self.assertEqual(state["sourceGenerationJobId"], "original-unknown")
            self.assertFalse(state["providerDispatched"])
            self.assertFalse(state["qualityPassed"])
            self.assertEqual((folder / "input.json").read_bytes(), evidence[self.entry["inputPath"]])
            lineage = json.loads((folder / "derivation.json").read_text())
            self.assertTrue(lineage["sourceFiles"])
            self.assertTrue(all(not Path(p).is_absolute() for p in lineage["sourceFiles"]))
            spec = importlib.util.spec_from_file_location("registration_fixture", ROOT / "output/textbook-full-audit-20261009/tools/register_structured_local_batch_v2.py")
            registration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(registration)
            (folder / "independent-static-review.json").write_text(canonical({**review,
                "classroomSha256": state["classroomSha256"], "inputSha256": state["inputSha256"], "publicationAllowed": False}))
            with patch.object(registration, "OWNED", self.root), patch.object(registration, "structural_review", return_value=review):
                self.assertEqual(registration.inspect_candidate(folder)[0]["classroomSha256"], state["classroomSha256"])
            (folder / "independent-static-review.json").unlink()
            broken = {**self.entry, "inputSha256": "0" * 64}
            with self.assertRaises(ValueError):
                compile_batch([self.entry, broken], self.root / "never-created")
            self.assertFalse((self.root / "never-created").exists())
            (folder / "classroom.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "immutable_output"):
                compile_batch([self.entry], target)
        self.assertTrue(all(Path(p).read_bytes() == raw for p, raw in evidence.items()))

    def test_revised_content_uses_new_preview_identity_without_changing_old_candidate(self):
        review = {"structuralChecksPassed": True, "issues": []}
        with patch("services.textbook_activity_compiler.OWNED", self.root), patch(
                "services.textbook_batch_queue_audio_service.structural_review", return_value=review):
            first = compile_batch([self.entry], self.root / "original")[0]
            original = Path(first["candidateDirectory"]) / "classroom.json"
            saved = original.read_bytes()
            self.design["title"] = "修改后的原创图片预习"
            self.freeze()
            revised = compile_batch([self.entry], self.root / "revised")[0]
            self.assertNotEqual(first["classroomId"], revised["classroomId"])
            self.assertEqual(original.read_bytes(), saved)
            self.assertEqual(compile_batch([self.entry], self.root / "revised")[0], revised)

    def test_unowned_or_symlink_output_not_written(self):
        from services.textbook_activity_compiler import owned_output
        occupied = self.root / "occupied"
        occupied.mkdir()
        (occupied / "paid-receipt.json").write_text("keep")
        link = self.root / "link"
        link.symlink_to(occupied, target_is_directory=True)
        with patch("services.textbook_activity_compiler.OWNED", self.root):
            for target in (occupied, link):
                with self.subTest(target=target), self.assertRaises(ValueError):
                    with owned_output(target):
                        self.fail("Unowned output was accepted")
        self.assertEqual((occupied / "paid-receipt.json").read_text(), "keep")
        self.assertEqual({p.name for p in occupied.iterdir()}, {"paid-receipt.json"})

    def execute(self, html, checks, model=False):
        node = shutil.which("node")
        if not node or not WORKER.is_file():
            self.skipTest("Node/linkedom pure-JS DOM fixture unavailable")
        code = 'import {parseHTML} from ' + json.dumps(WORKER.as_uri()) + ';import vm from "node:vm";import assert from "node:assert/strict";const html=' + json.dumps(html) + ';\n'
        code += r'''
const {window,document}=parseHTML(html);let calls=[],time=0,plays=0,frames=new Map(),nextFrame=0,draws=[];
window.parent={};window.miraNarrate=id=>{calls.push(id);return Promise.resolve(true);};
const gl=new Proxy({COMPILE_STATUS:1,LINK_STATUS:2,VERTEX_SHADER:3,FRAGMENT_SHADER:4,ARRAY_BUFFER:5,FLOAT:6,STATIC_DRAW:7,TRIANGLES:8,createShader(){return {};},getShaderParameter(){return true;},createProgram(){return {};},getProgramParameter(){return true;},createBuffer(){return {};},getAttribLocation(){return 0;},getUniformLocation(){return {};},drawArrays(...v){draws.push(v);}}, {get:(o,k)=>k in o?o[k]:()=>{}});
const canvas=document.getElementById('model-canvas');if(canvas){canvas.getContext=()=>gl;canvas.getBoundingClientRect=()=>({width:360,height:150});}
const video=document.querySelector('video');if(video){video.readyState=2;video.seeking=false;video.pause=()=>{};video.load=()=>{video.readyState=2;};video.play=()=>{plays++;return Promise.resolve();};Object.defineProperty(video,'currentTime',{get(){return time;},set(v){time=v;video.seeking=false;video.dispatchEvent(new window.Event('seeked'));}});}
const context=vm.createContext({window,document,console,AbortController,Float32Array,Math,Promise,Set,Map,Object,Array,Number,Error,setTimeout,clearTimeout,performance:{now:()=>time},location:{reload(){}},requestAnimationFrame(fn){const id=++nextFrame;frames.set(id,fn);return id;},cancelAnimationFrame(id){frames.delete(id);},ResizeObserver:class{observe(){}}});
vm.runInContext(Array.from(document.querySelectorAll('script')).find(s=>s.getAttribute('type')!=='application/json').textContent,context);
const run=s=>vm.runInContext(s,context),tick=()=>new Promise(r=>setImmediate(r));
function emit(cueId,status='ready'){const e=new window.Event('mira-narration-state');e.detail={cueId,status};window.dispatchEvent(e);}
function message(data,source=window.parent){const e=new window.Event('message');e.source=source;e.data=data;window.dispatchEvent(e);}
function click(id){document.getElementById(id).click();}
function frame(advance=0){time+=advance;const batch=Array.from(frames);batch.forEach(([id])=>frames.delete(id));batch.forEach(([,fn])=>fn(time));}
async function ended(){const id=calls.at(-1);emit(null);await tick();assert.equal(run('interactionBusy'),true);emit('foreign');await tick();assert.equal(run('interactionBusy'),true);emit(id);await tick();}
'''
        result = subprocess.run([node, "--input-type=module", "-e", code + checks + "\nrun('cancelOperation()');"], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_actual_game_wrong_retry_three_round_gates_hidden_and_progress(self):
        ir = self.ir()
        self.execute(game_scene(ir["scenes"][1], ir["assets"], ir["gameMode"]), r'''
assert.equal(document.querySelectorAll('[data-option].selected').length,0);click('start');await tick();await ended();await ended();
for(let i=0;i<3;i++){
 assert.equal(run('round'),i);assert.equal(document.getElementById('next').disabled,true);click('source');
 const wrong=run('config.rounds[round].optionAssetIds.find(k=>k!==config.rounds[round].targetAssetId)');run('choose('+JSON.stringify(wrong)+')');await tick();assert.equal(run('matched'),false);await ended();assert.equal(run('round'),i);
 run('choose(config.rounds[round].targetAssetId)');await tick();assert.equal(document.querySelectorAll('.paired .feedback-mark').length,1);assert.equal(run('feedbackReady'),false);click('next');assert.equal(run('round'),i);await ended();assert.equal(run('feedbackReady'),true);assert.equal(document.querySelectorAll('[data-progress].done').length,i+1);click('next');await tick();await ended();
}
click('reset');await tick();await ended();await ended();assert.equal(document.querySelectorAll('[data-progress].done').length,0);
click('source');run('choose(config.rounds[round].targetAssetId)');await tick();message({type:'MIRA_NARRATION_VISIBILITY',visible:false});await tick();assert.equal(run('interactionBusy'),false);assert.equal(document.getElementById('next').disabled,true);click('replay');await tick();await ended();assert.equal(document.getElementById('next').disabled,false);
''')

    def test_ant_transport_keeps_food_attached_and_gates_interrupted_narration(self):
        from content.chinese_animal_activity import ANT_CUE_KEYS, ant_scene
        scene = {"sceneId": "ant_transport", "title": "搬运食物", "adapterId": "ant_food_transport_v1",
                 "finiteCues": [{"cueId": "ant_" + str(i), "teacherText": "观察蚂蚁搬运食物。"}
                                for i in range(len(ANT_CUE_KEYS))]}
        scene.update({key: scene["finiteCues"][i]["cueId"] for i, key in enumerate(ANT_CUE_KEYS)})
        self.execute(ant_scene(scene, {}), r'''
assert.ok(draws.length>0);assert.equal(document.getElementById('pickup').disabled,true);
assert.ok(run('meshes.every(m=>Array.from(m.local).every(Number.isFinite))'));
click('start');await tick();await ended();const initial=run('JSON.stringify({antX,foodX,foodY,gait})');
click('pickup');await tick();frame(400);assert.ok(run('foodY>.12&&foodY<.57'));
document.hidden=true;document.dispatchEvent(new window.Event('visibilitychange'));await tick();
assert.equal(run('JSON.stringify({antX,foodX,foodY,gait})'),initial);
assert.equal(run('state'),'ready');assert.equal(document.getElementById('pickup').disabled,true);
document.hidden=false;document.dispatchEvent(new window.Event('visibilitychange'));
click('replay');await tick();await ended();click('pickup');await tick();frame(850);await tick();
assert.equal(run('state'),'loaded');assert.equal(document.getElementById('carry').disabled,true);
message({type:'MIRA_NARRATION_VISIBILITY',visible:false});await tick();
assert.equal(document.getElementById('carry').disabled,true);
click('replay');await tick();await ended();assert.equal(document.getElementById('carry').disabled,false);
click('carry');await tick();frame(900);assert.ok(run('antX>-1.45&&antX<1.10'));
assert.ok(run('Math.abs(foodX-antX-.83)<1e-8'));frame(950);await tick();
assert.equal(run('state'),'arrived');assert.equal(document.getElementById('drop').disabled,true);await ended();
click('rotate');assert.ok(run('poses.world.angle>0'));click('drop');await tick();frame(850);await tick();
assert.equal(run('state'),'delivered');assert.equal(run('foodX'),2.25);assert.ok(run('Math.abs(foodY-.12)<1e-8'));
assert.equal(document.getElementById('finish').disabled,true);await ended();
assert.equal(document.getElementById('finish').disabled,false);assert.equal(document.querySelectorAll('#ant-progress i.done').length,3);
click('reset');await tick();await ended();assert.equal(run('state'),'ready');assert.equal(run('poses.world.angle'),0);
assert.equal(document.getElementById('finish').disabled,true);
''', model=True)

    def test_sports_ball_motion_narration_and_interruption_gates(self):
        from content.chinese_sports_activity import SPORTS_CUE_KEYS, sports_scene
        scene = {"sceneId": "sports_ball", "title": "观察拍和踢", "adapterId": "hand_foot_ball_v1",
                 "dribbleAssetId": "hand", "kickAssetId": "foot",
                 "finiteCues": [{"cueId": "sports_" + str(i), "teacherText": "看看手和脚怎样使球移动。"}
                                for i in range(len(SPORTS_CUE_KEYS))]}
        scene.update({key: scene["finiteCues"][i]["cueId"] for i, key in enumerate(SPORTS_CUE_KEYS)})
        assets = {key: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 220" aria-label="'+key+'"><circle cx="120" cy="100" r="50"/></svg>'
                  for key in ("hand", "foot")}
        self.execute(sports_scene(scene, assets), r'''
assert.ok(draws.length>0);assert.equal(document.getElementById('dribble').disabled,true);
assert.equal(document.getElementById('finish').disabled,true);
assert.ok(run('meshes.every(m=>Array.from(m.local).every(Number.isFinite))'));
click('start');await tick();await ended();
const initial=run('JSON.stringify({actionMode,ballX,ballY,footX,footLift,handY})');
click('dribble');await tick();frame(500);assert.ok(run('ballY<.95'));
document.hidden=true;document.dispatchEvent(new window.Event('visibilitychange'));await tick();
assert.equal(run('JSON.stringify({actionMode,ballX,ballY,footX,footLift,handY})'),initial);
assert.equal(run('seen.size'),0);assert.equal(document.getElementById('kick').disabled,true);
document.hidden=false;document.dispatchEvent(new window.Event('visibilitychange'));
click('replay');await tick();await ended();click('dribble');await tick();frame(2050);await tick();
assert.equal(run('seen.size'),0);assert.equal(document.getElementById('kick').disabled,true);
await ended();assert.equal(run('seen.has("dribble")'),true);
assert.equal(document.getElementById('finish').disabled,true);
click('kick');await tick();frame(1000);assert.ok(run('ballX>.35&&ballX<2.10'));
frame(1050);await tick();assert.equal(run('seen.size'),1);await ended();
assert.equal(run('seen.size'),2);assert.ok(Math.abs(run('ballX')-2.10)<1e-8);
assert.equal(document.getElementById('finish').disabled,false);click('rotate');
assert.ok(run('poses.world.angle>0'));click('finish');await tick();await ended();
click('reset');await tick();await ended();assert.equal(run('seen.size'),0);
assert.equal(run('actionMode'),'dribble');assert.equal(document.getElementById('finish').disabled,true);
''', model=True)

    def test_picture_recall_requires_prompt_and_keeps_model_hidden_until_requested(self):
        from content.chinese_reading_activity import recitation_scene
        assets = {str(i): '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 220" aria-label="图画'+str(i)+'"><circle cx="100" cy="100" r="40"/></svg>' for i in range(3)}
        scene = {'sceneId':'recall', 'title':'看图试背', 'initialCueId':'intro', 'completeCueId':'done',
                 'pages':[{'assetId':str(i),'modelText':'传统句子。','promptCueId':'ask'+str(i),'modelCueId':'model'+str(i)} for i in range(3)],
                 'finiteCues':[{'cueId':key,'teacherText':'请看图试一试。'} for key in ['intro','done','ask0','model0','ask1','model1','ask2','model2']]}
        self.execute(recitation_scene(scene,assets), r'''
assert.ok(Array.from(document.querySelectorAll('[data-model-text]')).every(p=>p.hidden));
assert.equal(document.getElementById('next').disabled,true);click('start');await tick();
await ended();assert.equal(document.getElementById('model').disabled,true);await ended();
assert.equal(document.getElementById('next').disabled,false);assert.equal(calls.includes('model0'),false);
click('model');await tick();assert.equal(document.querySelector('[data-model-text]').hidden,false);
assert.equal(document.getElementById('next').disabled,true);
message({type:'MIRA_NARRATION_VISIBILITY',visible:false});await tick();
assert.equal(document.getElementById('next').disabled,true);
click('start');await tick();assert.equal(document.querySelector('[data-model-text]').hidden,true);await ended();await ended();
click('next');await tick();assert.equal(run('recallIndex'),1);await ended();
assert.equal(calls.includes('model1'),false);click('next');await tick();await ended();
click('model');await tick();await ended();click('next');await tick();await ended();
assert.equal(run('recallFinished'),true);assert.equal(document.getElementById('next').disabled,true);
assert.equal(document.querySelectorAll('[data-progress],.score').length,0);
click('reset');await tick();await ended();await ended();assert.equal(run('recallIndex'),0);
assert.ok(Array.from(document.querySelectorAll('[data-model-text]')).every(p=>p.hidden));
''')

    def test_wide_picture_game_preserves_far_side_objects_in_target_and_feedback(self):
        ir = self.ir()
        assets = {key: f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 400" role="img" aria-label="完整观察画面"><rect width="640" height="400" fill="#f7f3e8"/><g id="far-{key}"><circle cx="570" cy="290" r="22" fill="#7a9b94"/></g></svg>'
                  for key in ir["assets"]}
        self.execute(game_scene(ir["scenes"][1], assets, "visible_picture_matching"), r'''
click('start');await tick();await ended();await ended();for(let i=0;i<3;i++){const svg=document.querySelector('#source svg');assert.equal(svg.getAttribute('viewBox'),'0 0 640 400');assert.equal(svg.querySelector('circle').getAttribute('cx'),'570');click('source');run('choose(config.rounds[round].targetAssetId)');await tick();assert.equal(document.querySelector('#pair svg').getAttribute('viewBox'),'0 0 640 400');await ended();click('next');await tick();await ended();}
''')

    def test_spoken_wrong_then_replay_restores_same_round_target_and_end_gate(self):
        ir = self.ir()
        self.execute(game_scene(ir["scenes"][1], ir["assets"], "spoken_language_picture_matching"), r'''
click('start');await tick();await ended();await ended();for(let i=0;i<3;i++){
 const wrong=run('config.rounds[round].optionAssetIds.find(k=>k!==config.rounds[round].targetAssetId)');run('choose('+JSON.stringify(wrong)+')');await tick();assert.equal(calls.at(-1),run('config.retry'));await ended();click('replay');await tick();assert.equal(calls.at(-1),run('config.rounds[round].instructionCueId'));assert.equal(run('round'),i);assert.equal(run('matched'),false);assert.equal(document.getElementById('next').disabled,true);await ended();
 run('choose(config.rounds[round].targetAssetId)');await tick();message({type:'MIRA_NARRATION_VISIBILITY',visible:false});await tick();assert.equal(run('feedbackReady'),false);click('replay');await tick();assert.equal(calls.at(-1),run('config.rounds[round].matchCueId'));assert.equal(document.getElementById('next').disabled,true);await ended();assert.equal(document.getElementById('next').disabled,false);click('next');await tick();await ended();
}
''')

    def test_spoken_wrong_answer_uses_current_round_explanation_without_unlocking(self):
        ir = self.ir()
        scene = ir['scenes'][1]
        for i, row in enumerate(scene['rounds']):
            row['retryCueId'] = 'misconception_' + str(i)
            scene['finiteCues'].append({'cueId': row['retryCueId'],
                                       'teacherText': '数一数每个圆点，不要只看颜色。'})
        self.execute(game_scene(scene, ir['assets'], 'spoken_language_picture_matching'), r'''
click('start');await tick();await ended();await ended();
for(let i=0;i<3;i++){
 const wrong=run('config.rounds[round].optionAssetIds.find(k=>k!==config.rounds[round].targetAssetId)');
 run('choose('+JSON.stringify(wrong)+')');await tick();
 assert.equal(calls.at(-1),'misconception_'+i);
 assert.equal(document.getElementById('next').disabled,true);
 await ended();assert.equal(run('matched'),false);assert.equal(run('round'),i);
 assert.equal(document.querySelector('.selected'),null);
 click('replay');await tick();assert.equal(calls.at(-1),run('config.rounds[round].instructionCueId'));await ended();
 run('choose(config.rounds[round].targetAssetId)');await tick();
 assert.equal(document.getElementById('next').disabled,true);await ended();
 click('next');await tick();await ended();
}
''')

    def test_actual_video_seeks_before_cue_and_hidden_error_unlocks(self):
        ir = self.ir()
        from content.textbook_activity_templates import video_scene
        self.execute(video_scene(ir["scenes"][0], ir["assets"]), r'''
for(const i of [0,1,2]){run('observe(views['+i+'])');await tick();assert.equal(time,run('views['+i+'].seekSeconds'));assert.equal(calls.at(-1),run('views['+i+'].cueId'));await ended();}
run('start(false)');await tick();assert.equal(plays,0);await ended();assert.equal(plays,1);
run('observe(views[0])');await tick();message({type:'MIRA_NARRATION_VISIBILITY',visible:false});await tick();assert.equal(run('interactionBusy'),false);assert.equal(video.controls,true);
video.readyState=0;video.load=()=>{};const count=calls.length;run('observe(views[1])');await tick();video.dispatchEvent(new window.Event('error'));await tick();assert.equal(run('interactionBusy'),false);assert.equal(calls.length,count);assert.equal(document.getElementById('start').disabled,false);
''')

    def test_visible_game_only_current_three_pictures_accept_answers(self):
        ir = self.ir()
        scene = ir["scenes"][1]
        assets = {}
        for i, r in enumerate(scene["rounds"]):
            r["optionAssetIds"] = [str(i) + "-" + k for k in ("one", "three", "five")]
            r["targetAssetId"] = r["optionAssetIds"][i]
            assets.update({str(i) + "-" + k: svg for k, svg in ir["assets"].items()})
        self.execute(game_scene(scene, assets, "visible_picture_matching"), r'''
assert.equal(document.querySelectorAll('[data-option]').length,9);click('start');await tick();await ended();await ended();
for(let i=0;i<3;i++){
 const allowed=run('config.rounds[round].optionAssetIds');const visible=Array.from(document.querySelectorAll('[data-option]')).filter(b=>!b.hidden).map(b=>b.dataset.option);
 assert.deepEqual(visible,Array.from(allowed));assert.equal(visible.length,3);click('source');const count=calls.length;
 const forbidden=Array.from(document.querySelectorAll('[data-option]')).find(b=>b.hidden).dataset.option;
 run('choose('+JSON.stringify(forbidden)+')');await tick();assert.equal(calls.length,count);assert.equal(document.getElementById('pair').innerHTML,'');assert.equal(run('matched'),false);
 run('choose(config.rounds[round].targetAssetId)');await tick();await ended();click('next');await tick();await ended();
}
''')

    def test_actual_mesh_one_three_five_entities_before_cue_and_exact_end(self):
        ir = self.ir()
        self.execute(model_scene(ir["scenes"][2], ir["assets"]), r'''
assert.ok(draws.length>0);assert.ok(run('Object.values(geometries).every(g=>g.length%6===0&&g.every(Number.isFinite))'));
for(const [i,id]of ['one','three','five'].entries()){
 const before=calls.length;run('applyModel('+JSON.stringify(id)+')');await tick();assert.equal(calls.length,before);assert.equal(run('meshes.filter(m=>m.shape==="sphere"&&m.local[12]<0).length'),2*i+1);frame();frame();await tick();assert.equal(run('visited.size'),i);await ended();assert.equal(run('visited.size'),i+1);
}
assert.equal(document.getElementById('finish').disabled,false);const pose=run('JSON.stringify(poses.focus)');run('manipulate(.25,Math.PI/8)');assert.notEqual(run('JSON.stringify(poses.focus)'),pose);assert.equal(run('commitState("unknown")'),false);
run('reset()');await tick();frame();frame();await tick();await ended();assert.equal(document.getElementById('finish').disabled,true);
run('applyModel("one")');await tick();message({type:'MIRA_NARRATION_VISIBILITY',visible:false});await tick();frame();frame();await tick();assert.equal(run('interactionBusy'),false);assert.equal(run('visited.size'),0);
''', model=True)

    def test_actual_routes_exact_ids_four_native_commands_parent_guard(self):
        ir = self.ir()
        self.execute(route_scene(ir["scenes"][3], ir["assets"], ir["kind"]), r'''
for(let i=0;i<run('config.entries.length');i++){click('route-'+i);await tick();assert.equal(calls.at(-1),run('config.entries['+i+'].routeCueId'));await ended();}
const count=calls.length;message({type:'SET_WIDGET_STATE',state:{unitId:run('config.entries[0].unitId')}},{});await tick();assert.equal(calls.length,count);
message({type:'SET_WIDGET_STATE',state:{unitId:run('config.entries[0].unitId')}});await tick();assert.equal(run('assisted'),true);await ended();
message({type:'HIGHLIGHT_ELEMENT',target:'#route-0'});assert.ok(document.getElementById('route-0').classList.contains('teacher-hint'));message({type:'ANNOTATE_ELEMENT',target:'teacher-note',content:'观察图片。'});assert.equal(document.getElementById('teacher-note').textContent,'观察图片。');message({type:'REVEAL_ELEMENT',target:'observation-help'});assert.equal(document.getElementById('observation-help').hidden,false);
''')

    def test_all_admitted_semantic_mesh_families_change_real_geometry_not_labels(self):
        from content.textbook_activity_ir import STATES
        ir = self.ir()
        for key, states in STATES.items():
            scene = deepcopy(ir["scenes"][2])
            scene["modelAdapterKey"] = key
            scene["states"] = [{"sceneStateId": s, "observationCueId": "model_" + cue,
                                "assetId": cue} for s, cue in zip(states, ("one", "three", "five"))]
            if key == "chinese_zongzi_layers_scene":
                scene.update(adapterId="zongzi_layers_v1", openCueId="model_three", closeCueId="model_five")
                self.execute(model_scene(scene, ir["assets"]), r'''
assert.ok(draws.length>0);assert.equal(document.getElementById('close').disabled,true);
assert.equal(document.getElementById('finish').disabled,true);
click('start');await tick();await ended();const wrapped=run('JSON.stringify(meshes)');
assert.equal(run('meshes.some(m=>m.shape==="rice")'),false);
click('open');await tick();frame(450);assert.ok(run('openAmount>0&&openAmount<1'));
document.hidden=true;document.dispatchEvent(new window.Event('visibilitychange'));await tick();
assert.equal(run('openAmount'),0);assert.equal(run('state'),'wrapped');
assert.equal(document.getElementById('finish').disabled,true);
document.hidden=false;document.dispatchEvent(new window.Event('visibilitychange'));
click('start');await tick();await ended();click('open');await tick();frame(1100);await tick();
assert.equal(run('state'),'open');assert.equal(run('openAmount'),1);
assert.notEqual(run('JSON.stringify(meshes)'),wrapped);assert.ok(run('meshes.some(m=>m.shape==="rice")'));
assert.ok(run('meshes.some(m=>m.shape==="sphere"&&m.color[0]===.66)'));
assert.equal(document.getElementById('close').disabled,true);await ended();
click('rotate');assert.ok(run('poses.zongzi.angle>0'));
click('close');await tick();frame(1100);await tick();assert.equal(run('state'),'rewrapped');
assert.equal(run('openAmount'),0);assert.equal(run('JSON.stringify(meshes)'),wrapped);
assert.equal(document.getElementById('finish').disabled,true);await ended();
assert.equal(document.getElementById('finish').disabled,false);
click('reset');await tick();await ended();assert.equal(run('state'),'wrapped');
assert.equal(document.getElementById('finish').disabled,true);
''', model=True)
                continue
            if key == "chinese_well_bucket_scene":
                scene.update(adapterId="well_bucket_lift_v1", lowerCueId="model_three", raiseCueId="model_five")
                self.execute(model_scene(scene, ir["assets"]), r'''
assert.ok(draws.length>0);click('start');await tick();await ended();
const empty=run('JSON.stringify(meshes)');assert.equal(document.getElementById('raise').disabled,true);
click('lower');await tick();frame(1300);await tick();assert.equal(run('state'),'low_full');assert.equal(run('filled'),true);
const low=run('JSON.stringify(meshes)');await ended();click('raise');await tick();frame(1300);await tick();
assert.equal(run('state'),'high_full');assert.equal(run('bucketY'),1.5);const high=run('JSON.stringify(meshes)');await ended();
assert.equal(new Set([empty,low,high]).size,3);assert.equal(document.getElementById('finish').disabled,false);
''', model=True)
                continue
            checks = 'const states=' + json.dumps(states) + ';\n' + r'''
assert.ok(draws.length>0);const hashes=[];
for(const id of states){
 const before=calls.length;run('applyModel('+JSON.stringify(id)+')');await tick();assert.equal(calls.length,before);assert.equal(run('modelState'),id);frame();frame();await tick();assert.equal(calls.length,before+1);
 hashes.push(run('JSON.stringify({poses,meshes,geometry:meshes.map(m=>geometries[m.shape])})'));await ended();
}
assert.equal(new Set(hashes).size,3);assert.equal(run('visited.size'),3);assert.equal(document.getElementById('finish').disabled,false);assert.equal(run('commitState("unregistered")'),false);
'''
            if key == "english_travel_semantic_scene":
                checks += r'''
for(const id of states){run('commitState('+JSON.stringify(id)+')');const j=run('JSON.parse(JSON.stringify(journey))');assert.equal(j.mode,id.endsWith('_bike')?'bike':'bus');assert.equal(j.destination,id.startsWith('park_')?'park':'school');assert.equal(j.positions[j.mode][0],.65);assert.ok(run('meshes.some(m=>m.semanticKind==="school")'));assert.ok(run('meshes.some(m=>m.semanticKind==="park")'));}
'''
            with self.subTest(family=key):
                self.execute(model_scene(scene, ir["assets"]), checks, model=True)

    def test_spoken_game_hides_target_and_wrong_does_not_advance(self):
        ir = self.ir()
        scene = ir["scenes"][1]
        for r in scene["rounds"]:
            r["mode"] = "spoken_language_picture_matching"
        html = game_scene(scene, ir["assets"], "spoken_language_picture_matching")
        self.assertNotIn('id="source"', html)
        self.execute(html, r'''
assert.equal(document.querySelectorAll('[data-answer].selected').length,0);click('start');await tick();await ended();await ended();
for(let i=0;i<3;i++){
 assert.equal(run('round'),i);const wrong=run('config.rounds[round].optionAssetIds.find(k=>k!==config.rounds[round].targetAssetId)');run('choose('+JSON.stringify(wrong)+')');await tick();assert.equal(run('matched'),false);await ended();assert.equal(document.getElementById('next').disabled,true);
 run('choose(config.rounds[round].targetAssetId)');await tick();click('next');assert.equal(run('round'),i);await ended();assert.equal(document.querySelectorAll('[data-progress].done').length,i+1);click('next');await tick();await ended();
}
''')

    def test_ready_then_hidden_same_tick_does_not_grant_feedback_or_model_visit(self):
        ir = self.ir()
        self.execute(game_scene(ir["scenes"][1], ir["assets"], ir["gameMode"]), r'''
click('start');await tick();await ended();await ended();click('source');run('choose(config.rounds[round].targetAssetId)');await tick();
emit(calls.at(-1));message({type:'MIRA_NARRATION_VISIBILITY',visible:false});await tick();assert.equal(run('interactionBusy'),false);assert.equal(run('feedbackReady'),false);assert.equal(document.getElementById('next').disabled,true);assert.equal(document.querySelectorAll('[data-progress].done').length,0);
''')
        self.execute(model_scene(ir["scenes"][2], ir["assets"]), r'''
run('applyModel("one")');await tick();frame();frame();await tick();emit(calls.at(-1));message({type:'MIRA_NARRATION_VISIBILITY',visible:false});await tick();assert.equal(run('visited.size'),0);assert.equal(run('interactionBusy'),false);assert.equal(document.getElementById('finish').disabled,true);
''', model=True)

    def test_legacy_created_time_only_recovered_from_exact_parent_classroom(self):
        ir = self.ir()
        source = self.root / "source"
        classroom = render(ir, self.frozen, "exact-parent", 123456)
        state = json.loads((source / "state.json").read_text())
        state.pop("createdAt")
        state.update(status="generated_needs_review", classroomId=classroom["id"], classroomSha256=digest(classroom))
        (source / "state.json").write_text(canonical(state))
        (source / "classroom.json").write_text(canonical(classroom))
        self.assertEqual(preflight(self.entry)[2]["createdAt"], 123456)
        classroom["createdAt"] += 1
        (source / "classroom.json").write_text(canonical(classroom))
        with self.assertRaisesRegex(ValueError, "created_at_identity_changed"):
            preflight(self.entry)

    def test_english_unit_requires_language_family_and_exact_recipe_without_code(self):
        catalog = self.root / "english-catalog"
        catalog.mkdir()
        source = ROOT / "backend/content/textbooks/official-directories-v1/pep-wuxin-english-g6-lower-catalog.directory-689b6838c63afb7617806e25.json"
        (catalog / "book.json").write_bytes(source.read_bytes())
        _, tasks = build_plan(catalog, superseded_ids=set())
        task = next(t for t in tasks if t["kind"] == "unit_guide" and "Where did" in t["title"])
        self.frozen = freeze_input(task)
        self.design.update(kind="unit_guide", binding=self.frozen["binding"], manifestSha256=self.frozen["manifestSha256"],
                           originalLanguageIntroduction={"scope": "bounded original introduction, full source coverage unverified"})
        for r in self.design["scenes"][1]["rounds"]:
            r["mode"] = "spoken_language_picture_matching"
        model = self.design["scenes"][2]
        model["modelAdapterKey"] = "english_travel_semantic_scene"
        for state, key in zip(model["states"], ("park_bike", "park_bus", "school_bus")):
            state["sceneStateId"] = key
        route = self.design["scenes"][3]
        del route["entries"]
        node = self.frozen["directoryScope"][0]["lessons"][0]
        route["nodes"] = [{"nodeId": node["nodeId"], "title": node["title"], "sectionTitle": node["sectionTitle"], "routeCueId": "route_unit0"}]
        route["finiteCues"] = [c for c in route["finiteCues"] if c["cueId"] in {"route_intro", "route_finish", "route_unit0"}]
        self.design["finiteCues"] = [c for s in self.design["scenes"] for c in s["finiteCues"]]
        self.freeze()
        with self.assertRaisesRegex(ValueError, "explicit_route_picture"):
            self.ir()
        recipe = {"schemaVersion": "mira.textbook.activity-compiler-recipe.v1", "inputSha256": self.frozen["inputSha256"],
                  "activityDesignSha256": digest(self.design), "routeAssetIds": {node["nodeId"]: "one"}}
        def contract(value):
            return build_ir(self.frozen, self.design, expected_input_sha=self.entry["inputSha256"],
                expected_design_sha=self.entry["activityDesignSha256"], expected_scope_sha=self.entry["sourceScopeSha256"],
                expected_media_sha=self.entry["providedMediaSha256"], recipe=value)
        ir = contract(recipe)
        self.assertEqual(ir["scenes"][3]["nodes"][0]["assetId"], "one")
        for bad in ({**recipe, "inputSha256": "0" * 64}, {**recipe, "javascript": "anything"},
                    {**recipe, "routeAssetIds": {"unrelated-node": "one"}}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                contract(bad)
        self.design["scenes"][2]["modelAdapterKey"] = "bicycle_frame_pedal_steering"
        self.design["scenes"][2]["states"] = [{**s, "sceneStateId": key} for s, key in zip(model["states"], ("park", "pedal", "steer"))]
        self.freeze()
        with self.assertRaisesRegex(ValueError, "english_language_task_required"):
            self.ir()


if __name__ == "__main__":
    unittest.main()
