"""Admission for new releases; historical published classrooms stay readable."""
import hashlib
import json
from pathlib import Path

from content.textbook_catalog import digest
from content.textbook_interactive_narration import interactive_cues
from content.textbook_release import fail
from services.textbook_deepseek_authoring import check_blueprint, resolve_blueprint, STAGES

CONTRACT = "mira.textbook.deepseek-authored-release.v1"
ROOT = Path(__file__).resolve().parents[2] / "output"


def _artifact(path, expected):
    target = Path(path).resolve()
    if not target.is_relative_to(ROOT) or not target.is_file():
        fail("DeepSeek 教学凭据必须来自保留的本项目制作记录")
    raw = target.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        fail("DeepSeek 教学凭据原始字节已变化")
    return json.loads(raw)


def _pointer(value, pointer):
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        fail("教学文本来源引用无效")
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        try:
            value = value[int(token)] if isinstance(value, list) else value[token]
        except (KeyError, TypeError, IndexError, ValueError):
            fail("教学文本引用不存在")
    if not isinstance(value, str) or not value.strip():
        fail("教学文本引用必须指向实际的逐字讲解")
    return value


def validate_new_authoring(original, classroom, review):
    """An actual response, applied narration and a separate content review."""
    proof = original.get("activityDesign", {}).get("deepseekAuthoring")
    if not isinstance(proof, dict) or proof.get("schemaVersion") != CONTRACT:
        fail("新课件须有真实 DeepSeek 教案和逐字讲解凭据，直接编写草稿不能发布")
    request = _artifact(proof.get("requestPath", ""), proof.get("requestByteSha256"))
    response = _artifact(proof.get("responsePath", ""), proof.get("responseByteSha256"))
    if (request.get("requestSha256") != digest({k: v for k, v in request.items() if k != "requestSha256"})
            or request.get("providerId") != "deepseek"
            or request.get("payload", {}).get("model") != "deepseek-v4-pro"
            or request.get("taskId") != original["taskId"]
            or request.get("source", {}).get("binding") != original["binding"]
            or request["source"].get("manifestSha256") != original["manifestSha256"]
            or not response.get("id") or not response.get("model", "").startswith("deepseek-v4-pro")):
        fail("DeepSeek 教学请求与教材或模型身份不一致")
    try:
        choice = response["choices"][0]
        if choice.get("finish_reason") != "stop":
            fail("DeepSeek 教学回答尚未完整返回")
        blueprint = resolve_blueprint(request, response)
        check_blueprint(blueprint, request["source"])
    except (KeyError, IndexError, TypeError, ValueError):
        fail("DeepSeek 教学回答结构或逐目标证据无效")
    if proof.get("blueprintSha256") != digest(blueprint):
        fail("本地制作使用的 DeepSeek 教案已变化")
    scope = original.get("reviewedLessonScope") or original.get("activityDesign", {}).get("reviewedTeachingScope", {})
    if (set(scope.get("activityGoalIds", [])) != set(request["source"]["activityGoalIds"])
            or scope.get("outstandingGoalIds", []) != blueprint["outstandingGoalIds"]):
        fail("本地制作丢失教学目标或隐瞒未完成范围")
    actual = {}
    for scene in classroom["scenes"]:
        if scene.get("type") == "interactive":
            for cue in interactive_cues(scene["content"]["html"]):
                if cue["id"] in actual:
                    fail("课件旁白身份重复")
                actual[cue["id"]] = {"text": cue["text"], "sceneId": scene["id"]}
    mapping = proof.get("cueOrigins", [])
    if not isinstance(mapping, list) or {m.get("cueId") for m in mapping} != set(actual) or len(mapping) != len(actual):
        fail("课件全部旁白必须追溯到生成文本或已核实的逐笔控制")
    activities = {a["activityId"]: a for a in blueprint["activities"]}
    covered = set()
    origins = {}
    mechanical = scope.get("strokeOrderReference", {}).get("characters", {})
    if isinstance(mechanical, list):
        mechanical = {c["character"]: c for c in mechanical}
    for origin in mapping:
        cue = actual[origin["cueId"]]
        if cue["sceneId"] != origin.get("sceneId"):
            fail("教学来源引用了其他场景")
        method = origin.get("method")
        if method == "deepseek_exact":
            text = _pointer(blueprint, origin.get("pointer"))
            if cue["text"] != text:
                fail("本地程序改写了 DeepSeek 逐字教学内容，须保留模型修订依据")
            if origin["pointer"].startswith("/activities/"):
                try:
                    activity = blueprint["activities"][int(origin["pointer"].split("/")[2])]
                except (IndexError, ValueError):
                    fail("DeepSeek 活动引用无效")
                if origin.get("activityId") != activity["activityId"]:
                    fail("旁白与 DeepSeek 活动身份不一致")
                if origin["pointer"].endswith("/teacherText"):
                    covered.add(activity["activityId"])
        elif method == "verified_stroke_control":
            entry = mechanical.get(origin.get("character"), {})
            names = entry.get("names", entry.get("strokeNames", []))
            index = origin.get("strokeIndex")
            if type(index) is not int or not 0 <= index < len(names) or cue["text"] != names[index]:
                fail("逐笔控制旁白必须来自已核实的笔画名称")
        else:
            fail("教学旁白不得回退到未经生成的本地教学模板")
        origins[origin["cueId"]] = origin
    if covered != set(activities):
        fail("本地课件没有完整制作 DeepSeek 教案中的教学环节")
    depth = review.get("teachingDepthReview", {})
    if (depth.get("schemaVersion") != CONTRACT or depth.get("status") != "passed"
            or depth.get("blueprintSha256") != digest(blueprint)
            or depth.get("sourceSha256") != digest(classroom)
            or depth.get("unresolvedFindings") != [] or not depth.get("reviewer")
            or depth.get("outstandingGoalIds") != blueprint["outstandingGoalIds"]):
        fail("新课件需要针对实际教学内容的逐目标深度审核")
    evidence = depth.get("goalEvidence", [])
    goals = set(request["source"]["activityGoalIds"])
    if len(evidence) != len(goals) or {e.get("goalId") for e in evidence} != goals:
        fail("深度审核未覆盖全部已声明目标")
    for row in evidence:
        if not row.get("basis"):
            fail("深度审核缺少具体依据")
        for phase in STAGES:
            refs = row.get(phase, [])
            if not refs:
                fail("深度审核缺少解释、示范、带练、迁移、纠错或回想")
            for ref in refs:
                origin = origins.get(ref.get("cueId"), {})
                activity = activities.get(origin.get("activityId"), {})
                if (origin.get("method") != "deepseek_exact" or origin.get("sceneId") != ref.get("sceneId")
                        or row["goalId"] not in activity.get("goalIds", [])):
                    fail("深度审核引用的真实讲解或目标不匹配")
    return {"schemaVersion": CONTRACT, "providerId": "deepseek", "modelId": response["model"],
            "responseId": response["id"], "requestSha256": request["requestSha256"],
            "responseByteSha256": proof["responseByteSha256"], "blueprintSha256": digest(blueprint),
            "sourceSha256": digest(classroom), "depthReviewSha256": digest(depth),
            "goalCount": len(goals), "activityCount": len(activities), "narrationCount": len(actual)}


def validate_new_release_admission(frozen, review):
    proof = review.get("deepseekAuthoringAdmission")
    if (not isinstance(proof, dict) or proof.get("schemaVersion") != CONTRACT
            or frozen.get("deepseekAuthoringAdmissionSha256") != digest(proof)
            or proof.get("providerId") != "deepseek"
            or proof.get("sourceSha256") != frozen.get("sourceSha256")
            or proof.get("depthReviewSha256") != digest(review.get("teachingDepthReview"))):
        fail("新发布缺少已绑定的 DeepSeek 教学来源及深度审核")
