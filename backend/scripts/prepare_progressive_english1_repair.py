"""Assemble the audited, terminal English first-set repair without dispatching."""
from copy import deepcopy
from hashlib import sha256
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "output/progressive-preview/saved-stage-english-slot1"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return sha256(canonical(value).encode()).hexdigest()


def write_once(name, value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    path = BASE / name
    if path.exists():
        assert path.read_bytes() == raw, f"Archived proposal differs: {name}"
    else:
        with path.open("xb") as stream:
            path.chmod(0o600)
            stream.write(raw)
    return sha256(raw).hexdigest()


def write_revision(name, value):
    recovery = ROOT / "openmaic-runtime/.runtime/OpenMAIC/data/formal-saved-stage-recoveries/omformal_35329ccda267db6155963636"
    assert not (recovery / "completion.json").exists() and not list(recovery.glob("complete*.claim")), "Completion has already been attempted"
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    path = BASE / name
    if path.exists() and path.read_bytes() != raw:
        old = json.loads(path.read_bytes())
        write_once(name.replace(".json", "-" + sha256(path.read_bytes()).hexdigest() + ".json"), old)
    write_once(name.replace(".json", "-" + sha256(raw).hexdigest() + ".json"), value)
    temporary = path.with_suffix(".tmp")
    with temporary.open("xb") as stream:
        temporary.chmod(0o600)
        stream.write(raw)
    temporary.replace(path)
    return sha256(raw).hexdigest()


source_raw = (BASE / "source-document.json").read_bytes()
source = json.loads(source_raw)
audit = json.loads((BASE / "source-audit.json").read_text())
assert sha256(source_raw).hexdigest() == audit["sourceDocumentSha256"]
assert audit["sourceJobSha256"] == "9229b9a216abfaa5e7b30a87140e758a7b2d67186843f5fef1c06d8b7f0e1ab1"
assert audit["sourceSnapshotSha256"] == "3dc53e84a8fe5228041f8edb4f66948e3501b7e9ac7ece2064d8aac316b38970"
source_by_id = {s["id"]: s for s in source["scenes"]}
scenes = deepcopy(source_by_id)
inputs = {}
for page, filename in ((2, "english-slot1-p2-repaired.json"), (8, "english-slot1-p8-repaired-scene.json")):
    path = BASE.parent / filename
    raw = path.read_bytes()
    candidate = json.loads(raw)
    original = source_by_id[f"scene-p{page}"]
    assert all(candidate[k] == original[k] for k in ("id", "type", "stageId", "createdAt", "outlineId"))
    assert set(candidate) == set(original)
    scenes[candidate["id"]] = candidate
    inputs[str(path)] = sha256(raw).hexdigest()

game_path = BASE.parent / "english-slot1-p3-repair-proposal.json"
game_raw = game_path.read_bytes()
game = json.loads(game_raw)
assert game["sourceDocumentFileSha256"] == audit["sourceDocumentSha256"]
assert game["sourceSnapshotSha256"] == audit["sourceSnapshotSha256"] and game["sceneId"] == "scene-p3"
changes = {change["path"]: change["value"] for change in game["changes"]}
assert set(changes) == {"/content/html", "/actions"} and len(game["changes"]) == 2
assert len(changes["/actions"]) == len(source_by_id["scene-p3"]["actions"])
for original, repaired in zip(source_by_id["scene-p3"]["actions"], changes["/actions"]):
    if original["id"] == "action_OIZlqpZG":
        assert {**original, "text": repaired["text"]} == repaired
    else:
        assert original == repaired
scenes["scene-p3"]["content"]["html"] = changes["/content/html"]
scenes["scene-p3"]["actions"] = changes["/actions"]
inputs[str(game_path)] = sha256(game_raw).hexdigest()


def text(page, element_id, old, new):
    element = next(e for e in scenes[f"scene-p{page}"]["content"]["canvas"]["elements"] if e["id"] == element_id)
    assert old in element["content"]
    element["content"] = element["content"].replace(old, new)


def speech(page, action_id, value):
    action = next(a for a in scenes[f"scene-p{page}"]["actions"] if a["id"] == action_id)
    assert action["type"] == "speech"
    action["text"] = value


# Teach grammatical roles, not physical word position as a universal rule.
scenes["scene-p1"]["title"] = "I 和 me，角色决定形式"
text(1, "text_WxsK_iu9", "I 和 me，位置说了算", "I 和 me，角色决定形式")
text(1, "text_chWLvzhs", "我站在句子的哪个位置？", "谁喜欢猫？")
text(1, "text_z3XYYjcH", "我站在句子的哪个位置？", "猫喜欢谁？")
text(1, "text_mHs1GfBu", "位置：主语（句首）", "角色：主语，用主格 I")
text(1, "text_XyA6k0TV", "位置：宾语（动后）", "角色：likes 的宾语，用 me")
speech(1, "action_4IeCg6IE", "左边是 I like the cat，意思是我喜欢这只猫。谁喜欢猫？是我。这里 I 作主语，用主格。")
speech(1, "action_A4b5-yW4", "右边是 The cat likes me，意思是这只猫喜欢我。猫喜欢谁？是我。这里 me 作动词 likes 的宾语，用宾格。")
speech(1, "action_x3LR6EzN", "两句话里的 I 和 me 都指同一个我。作主语和作宾语是两种不同的角色，因此使用的代词形式不同。")
speech(1, "action_xqlgdNbT", "判断时先弄清代词指谁，再看它作主语还是作动词宾语。接下来先认本课词义，再学习两套代词的配对。")

# Keep the vocabulary shown on the slide aligned with the spoken lesson.
speech(7, "action_twlTG1FR", "左边还有 homework，意思是家庭作业；see，意思是看见。接着看中间一列。")
speech(7, "action_2EF_JEUF", "中间还有 watch，意思是观看；follow，意思是跟随。接着看右边一列。")
speech(7, "action_DXDcEUV8", "thank 的意思是感谢。句子中还会看到 calls、watches 和 follows，它们分别来自 call、watch 和 follow；这里的词义保持不变。")
speech(7, "action_SgX1xnX9", "现在词义准备好了。下面先学习代词配对，再通过三维演示和游戏练习判断代词的角色。")

# Clear, usable recap instructions and a self-contained reference example.
speech(6, "action_zbrHVMZO", "最后回顾今天的代词配对：I 和 me，he 和 him，she 和 her，we 和 us，they 和 them。you 和 it 的主格、宾格形式相同。")
speech(6, "action_NGSQW9Ka", "对照这张表，试着说出三组配对，再解释它们分别在什么角色下使用。")
speech(6, "action_gCploof0", "先读 He is my friend，意思是他是我的朋友。接着用 I thank him 表示我感谢他。同一个他，为什么从 he 变成 him？请根据主语和宾语的角色来解释。")
speech(5, "action_x86fknbG", "现在请独立完成这五道题。先读懂句子，再判断空位作主语还是作动词宾语，选出正确的代词形式。")

order = ["scene-p1", "scene-p7", "scene-p2", "scene-p8", "scene-p3", "scene-p4", "scene-p5", "scene-p6"]
assert set(order) == set(scenes) and len(order) == len(scenes)
# The runtime stores the single course-wide interaction plan in the FIRST
# interactive page. Relocate its unchanged data with the page reorder; its
# objective still targets the actual five-state game on p3.
plan_pattern = re.compile(r'<script\b(?=[^>]*\bid=["\']mira-interaction-plan["\'])(?=[^>]*\btype=["\']application/json["\'])[^>]*>[\s\S]*?</script\s*>', re.I)
game_html = scenes["scene-p3"]["content"]["html"]
plan_scripts = plan_pattern.findall(game_html)
assert len(plan_scripts) == 1 and not plan_pattern.search(scenes["scene-p8"]["content"]["html"])
scenes["scene-p3"]["content"]["html"] = game_html.replace(plan_scripts[0], "", 1)
scene_html = scenes["scene-p8"]["content"]["html"]
assert scene_html.count("</body>") == 1
scenes["scene-p8"]["content"]["html"] = scene_html.replace("</body>", plan_scripts[0] + "</body>", 1)
result = []
for index, scene_id in enumerate(order, start=1):
    scene = scenes[scene_id]
    scene["order"] = index
    result.append(scene)

assert [s["id"] for s in result if s["type"] == "quiz"] == ["scene-p4", "scene-p5"]
for scene in result:
    original = source_by_id[scene["id"]]
    assert all(scene[k] == original[k] for k in ("id", "type", "stageId"))
    if scene["type"] == "quiz":
        assert scene["content"] == original["content"], "Frozen quiz content changed"

# The source and previous media receipts remain intact. New action identities
# keep the revised classroom from colliding with an old audio request identity.
revision_seed = digest({"sourceSnapshotSha256": audit["sourceSnapshotSha256"], "scenes": result})
id_mappings = []
serialized = canonical(result)
for scene in result:
    for action in scene.get("actions", []):
        if action["type"] != "speech":
            continue
        old_id = action["id"]
        assert serialized.count(json.dumps(old_id)) == 1, f"Speech ID is referenced elsewhere: {old_id}"
        action["id"] = "action_" + digest({"revision": revision_seed, "scene": scene["id"], "action": old_id})[:40]
        id_mappings.append({"sceneId": scene["id"], "originalId": old_id, "revisedId": action["id"]})
assert len({m["revisedId"] for m in id_mappings}) == len(id_mappings)
proposal_sha = write_revision("repair-proposal.json", {"scenes": result})
repair_audit = {"schemaVersion": "mira.progressive-english1-saved-stage-proposal.v1",
    "sourceJobSha256": audit["sourceJobSha256"], "sourceSnapshotSha256": audit["sourceSnapshotSha256"],
    "sourceDocumentSha256": audit["sourceDocumentSha256"], "proposalSha256": proposal_sha,
    "candidateFiles": inputs, "sceneOrder": order, "revisionSeed": revision_seed,
    "speechIdMappings": id_mappings, "originalAudioPreserved": True, "newAudioRequired": True,
    "preservedQuizContent": True, "preservedQuizRelativeOrder": True, "preservedFormalInput": True,
    "interactionPlanRelocation": {"from": "scene-p3", "to": "scene-p8", "scriptSha256": sha256(plan_scripts[0].encode()).hexdigest(), "planContentUnchanged": True},
    "sceneContentChanges": [{"sceneId": s["id"], "sourceSha256": digest(source_by_id[s["id"]]),
                             "repairedSha256": digest(s)} for s in result]}
audit_sha = write_revision("repair-audit.json", repair_audit)
print(json.dumps({"status": "proposal_prepared", "providerCalls": 0, "databaseWrites": 0,
                  "proposalSha256": proposal_sha, "auditSha256": audit_sha,
                  "speechCount": len(id_mappings), "sceneOrder": order}))
