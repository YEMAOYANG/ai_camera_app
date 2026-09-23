"""Prepare the exact English1 vocabulary narration revision; no external calls."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / "output/progressive-preview/saved-stage-english-slot1"
OUT = ROOT / "output/progressive-preview/saved-stage-english-slot1-revision2"
NATIVE = ROOT / "openmaic-runtime/.runtime/OpenMAIC"
JOB = "omformal_35329ccda267db6155963636"
PRIOR_SNAPSHOT = "ce327bcb84a0836065def3bc20fcfe62ede100a099be5194df5b4c8014c2d8a9"


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def immutable(name, raw):
    path = OUT / name
    if path.exists():
        assert path.read_bytes() == raw, f"Archive already differs: {name}"
    else:
        with path.open("xb") as stream:
            path.chmod(0o600)
            stream.write(raw)
    return sha256(raw).hexdigest()


def save(name, value):
    return immutable(name, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


prior_raw = (OLD / "repair-proposal.json").read_bytes()
prior_audit_raw = (OLD / "repair-audit.json").read_bytes()
assert sha256(prior_raw).hexdigest() == "b39a30128047803f3438f51e24a1a821a7a06c931ee84ff8e3cc6763b918f0ba"
assert sha256(prior_audit_raw).hexdigest() == "cf3d84b08a9c0fe1061510b8a39e3f0f6a0ee7efb8f66841993f2c4ff7bceabe"
source = json.loads(prior_raw)
proposal = deepcopy(source)
edits = {
    "跟我读：call，打电话。": "跟我读：call 的中文意思是打电话。",
    "invite，邀请。": "invite 的中文意思是邀请。",
    "party，聚会。": "party 的中文意思是聚会。",
    "ask，问。": "ask 的中文意思是问。",
    "help，帮助。": "help 的中文意思是帮助。",
    "like，喜欢。": "like 的中文意思是喜欢。",
    "draw，画。": "draw 的中文意思是画。",
    "drink，喝。": "drink 的中文意思是喝。",
    "open，打开。": "open 的中文意思是打开。",
}
changes = []
for scene in proposal["scenes"]:
    if scene["id"] != "scene-p7":
        continue
    for action in scene.get("actions", []):
        if action["type"] == "speech" and action["text"] in edits:
            original = action["text"]
            action["text"] = edits[original]
            changes.append({"sceneId": scene["id"], "actionId": action["id"], "before": original, "after": action["text"]})
assert len(changes) == len(edits) == 9

revision_seed = digest({"policy": "mira.english1.gloss-context-revision.v1", "priorSnapshotSha256": PRIOR_SNAPSHOT, "proposal": proposal})
mappings = []
serialized = json.dumps(proposal, ensure_ascii=False)
for scene in proposal["scenes"]:
    for action in scene.get("actions", []):
        if action["type"] != "speech":
            continue
        original_id = action["id"]
        # Source speech IDs occur once, solely as their action definition.
        assert serialized.count(original_id) == 1
        action["id"] = "action_" + digest({"revision": revision_seed, "sceneId": scene["id"], "originalId": original_id})[:40]
        mappings.append({"sceneId": scene["id"], "originalId": original_id, "revisedId": action["id"]})
assert len(mappings) == len({m["revisedId"] for m in mappings}) == 42
for old, new in zip(source["scenes"], proposal["scenes"]):
    assert {k: v for k, v in old.items() if k != "actions"} == {k: v for k, v in new.items() if k != "actions"}
    assert len(old["actions"]) == len(new["actions"])
    for before, after in zip(old["actions"], new["actions"]):
        if before["type"] != "speech":
            assert before == after
        else:
            expected = dict(before, id=after["id"])
            if old["id"] == "scene-p7" and before["text"] in edits:
                expected["text"] = edits[before["text"]]
            assert expected == after

OUT.mkdir(parents=True, exist_ok=True)
for name in ("source-document.json", "source-snapshot.json", "source-audit.json", "original-native-job.json", "manifest.json"):
    immutable(name, (OLD / name).read_bytes())
immutable("previous-repair-proposal.json", prior_raw)
immutable("previous-repair-audit.json", prior_audit_raw)
recovery = NATIVE / "data/formal-saved-stage-recoveries" / JOB
for name in ("prepared-snapshot.json", "browser-preflight.json", f"complete-{PRIOR_SNAPSHOT}.claim"):
    immutable("previous-" + name, (recovery / name).read_bytes())
source_audit = json.loads((OLD / "source-audit.json").read_bytes())
proposal_sha = save("repair-proposal.json", proposal)
audit = {
    "schemaVersion": "mira.progressive-english1-gloss-revision.v1",
    "sourceJobSha256": source_audit["sourceJobSha256"],
    "sourceSnapshotSha256": source_audit["sourceSnapshotSha256"],
    "sourceDocumentSha256": source_audit["sourceDocumentSha256"],
    "previousRepairSnapshotSha256": PRIOR_SNAPSHOT,
    "previousProposalSha256": sha256(prior_raw).hexdigest(),
    "previousAuditSha256": sha256(prior_audit_raw).hexdigest(),
    "proposalSha256": proposal_sha,
    "reason": "已完成的原ASR、repair1及自动语言ASR均将短语 ask，问。识别为 Ask when.；为孤立词义增加清晰中文语境，教学词义不变。",
    "speechTextChanges": changes,
    "speechIdMappings": mappings,
    "revisionSeed": revision_seed,
    "sceneContentUnchanged": True,
    "quizContentUnchanged": True,
    "sceneOrderUnchanged": True,
    "formalInputUnchanged": True,
    "oldAudioPreserved": True,
    "newQualityReviewRequired": True,
    "newAudioRequired": True,
}
audit_sha = save("repair-audit.json", audit)
print(json.dumps({"status": "revision_prepared", "proposalSha256": proposal_sha,
                  "auditSha256": audit_sha, "speechTextChanges": len(changes), "newSpeechIds": len(mappings),
                  "directory": str(OUT), "providerCalls": 0, "databaseWrites": 0}, ensure_ascii=False))
