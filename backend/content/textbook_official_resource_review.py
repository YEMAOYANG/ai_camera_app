"""Validate a recorded official-resource review, never fetch or attest learning.

This is a new-authoring input gate. Historical frozen jobs must remain readable
without this record; callers apply it only before preparing or dispatching new
work. Complete fields do not prove that somebody watched a video or that an
adaptation is pedagogically sound.
"""
from __future__ import annotations

from datetime import date, datetime
import re
from urllib.parse import parse_qs, urlsplit

from content.textbook_catalog import digest


SCHEMA = "mira.official-textbook-resource-review.v1"
VIDEO_MODALITY_REVIEW_SCHEMA = "mira.official-video-modality-review.v1"
POST_CLASS_PRACTICE_SCHEMA = "mira.textbook.post-class-practice.v1"
LEGACY_COURSE_IDENTITY_SCHEMA = "mira.smartedu.legacy-course-identity.v1"
REQUIRED_RESOURCES = (
    "video", "courseware", "teachingDesign", "learningTaskSheet", "afterClassExercise",
)
WAIVABLE_UNAVAILABLE_RESOURCES = frozenset({"video", "courseware"})
UNWAIVABLE_RESOURCES = ("teachingDesign", "learningTaskSheet", "afterClassExercise")
BINDING_FIELDS = (
    "editionId", "revisionId", "nodeId", "gradeCode", "subject", "volume", "schoolSystem",
)
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_AUTH_QUERY = re.compile(r"token|signature|credential|auth|access.?key|secret|session|policy|security|(?:^|[-_])sign(?:$|[-_])|(?:^|[-_])key(?:$|[-_])", re.I)
_BLOCKED_NOTE = re.compile(r"登录|登入|鉴权|无权限|权限不足|加载失败|无法加载|打不开|无法访问|未阅读|未观看|待阅读|待观看|404|403|login|sign.?in|unauthori|forbidden|unread|pending|load.?fail", re.I)
_ABSENCE_NOTE = re.compile(r"未提供|没有提供|未列出|没有列出|未设置|无[^。；\n]{0,24}(?:资源|任务单|练习|课件|设计|视频)|not provided|not listed", re.I)
_OFFICIAL_NOTE = re.compile(r"官方|官网|资源列表|资源清单|official", re.I)
# Match disclosures about this resource review, not generic teaching findings
# such as "学生尚未掌握" or "先自主阅读再教师示范". These checks only reject
# explicit contradictions of status=reviewed; they do not attest actual viewing.
_REVIEW_PREFIX = r"(?:(?:我|我们|本次|目前|当前|暂时|审阅者|实际审阅|审阅状态)\s*(?:[:：]\s*)?)?"
_RESOURCE_NAME = r"(?:视频|课件|教学设计|学习任务单|课后练习|任务单|练习|本资源|该资源|对应资源|正文|全文|材料)"
_NOT_READ = r"(?:尚未|还未|还没有|还没|未完成|未能|未曾|没有|没能|未|没)(?:实际|完整|真正)?(?:观看|看完|阅读|读完|审阅|看|读)"
_UNREAD_DISCLOSURE = re.compile(
    r"^" + _REVIEW_PREFIX + r"(?:"
    + _NOT_READ + r"(?:\s*$|\s*(?:该|本|这个|整个|完整的|全部|对应的)?" + _RESOURCE_NAME + r")"
    + r"|" + _RESOURCE_NAME + r"\s*" + _NOT_READ + r"(?:\s*$|(?:完成|完毕|完)\s*$)"
    + r"|(?:资源)?审阅(?:尚未完成|未完成|待完成)"
    + r"|(?:not\s+(?:yet\s+)?(?:read|watched|reviewed)|unread|pending\s+review)\b)", re.I,
)
_TITLE_ONLY_DISCLOSURE = re.compile(
    r"^" + _REVIEW_PREFIX
    + r"(?:(?:只|仅|仅仅)(?:能)?(?:看到|看见|读到|浏览|查看)[^，,。；;\n]{0,16}(?:标题|封面|目录|摘要)"
    + r"|(?:只|仅)(?:有|显示|可见)(?:标题|封面|目录|摘要)|title\s+only\b)", re.I,
)
_ACCESS_DISCLOSURE = re.compile(
    r"^" + _REVIEW_PREFIX + r"(?:"
    + r"(?:登录|登入|鉴权)(?:受阻|失败)|(?:无权限|权限不足|加载失败|打不开)"
    + r"|(?:需要|需先|必须先)登录"
    + r"|(?:页面|资源|视频|课件)?(?:无法|不能|未能|没能)(?:访问|打开|加载|播放|获取|观看)"
    + r"|(?:页面)?(?:404|403)\b"
    + r"|(?:待|等待)(?:获取|下载|读取|观看|阅读)" + _RESOURCE_NAME
    + r"|(?:login\s+(?:required|blocked|failed)|access\s+denied|load\s+failed)\b)", re.I,
)
_TIMECODE = re.compile(r"(?:\d{1,3}:)?[0-5]?\d:[0-5]\d\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_AUDIO_TEXT_ONLY = re.compile(
    r"(?:(?:仅|只|only)[^，,。；;\n]{0,28}(?:字幕|文字稿|转写|ASR|subtitle|transcript)"
    r"|(?:字幕|文字稿|转写|ASR|subtitle|transcript)[^，,。；;\n]{0,28}"
    r"(?:代替|替代|冒充|等同|only))", re.I,
)
_AUDIO_NOT_HEARD = re.compile(
    r"(?:未|没有|没能|无法|不能|尚未|not\s+(?:actually\s+)?(?:heard|listened))"
    r"[^，,。；;\n]{0,20}(?:听|听审|音轨|音频|audio|track)"
    r"|(?:音轨|音频|audio|track)[^，,。；;\n]{0,20}"
    r"(?:未听|未审|不可得|无法取得|没有输出|unavailable|not\s+heard)", re.I,
)
_AUDIO_ACCESS_BLOCKED = re.compile(
    r"DRM|401|403|私有|private|鉴权|登录|令牌|token|无法取得|不能取得|无法获取|不能获取|"
    r"未输出|没有输出|不可访问|access\s+denied|unauthori", re.I,
)


class OfficialResourceReviewError(ValueError):
    """Stable diagnostic codes contain neither source contents nor credentials."""


def _require(condition, code):
    if not condition:
        raise OfficialResourceReviewError(code)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _texts(value):
    return isinstance(value, list) and bool(value) and all(_text(item) for item in value)


def _review_time(value, code):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        _require(parsed.tzinfo is not None, code)
        return parsed
    except OfficialResourceReviewError:
        raise
    except (TypeError, ValueError, AttributeError):
        raise OfficialResourceReviewError(code) from None


def _timecode_seconds(value):
    _require(isinstance(value, str) and _TIMECODE.fullmatch(value),
             "official_video_modality_interval_invalid")
    parts = [int(part) for part in value.split(":")]
    if len(parts) == 2:
        minutes, seconds = parts
        return minutes * 60 + seconds
    hours, minutes, seconds = parts
    return hours * 3600 + minutes * 60 + seconds


def _review_intervals(value, *, required):
    _require(isinstance(value, list) and (bool(value) if required else not value),
             "official_video_modality_interval_invalid")
    seen = set()
    for interval in value:
        _require(isinstance(interval, dict) and set(interval) == {"start", "end"},
                 "official_video_modality_interval_invalid")
        start, end = interval.get("start"), interval.get("end")
        _require((start, end) not in seen and _timecode_seconds(start) < _timecode_seconds(end),
                 "official_video_modality_interval_invalid")
        seen.add((start, end))


def _modality_common(value, *, fields, reviewer, completed_at, intervals_required, code):
    _require(isinstance(value, dict) and set(value) == fields
             and _text(value.get("method")) and value.get("reviewedBy") == reviewer
             and _texts(value.get("findings")), code)
    reviewed_at = _review_time(value.get("reviewedAt"), code)
    _require(reviewed_at <= completed_at, code)
    _review_intervals(value.get("intervals"), required=intervals_required)


def _supporting_text_evidence(value):
    _require(isinstance(value, list), "official_video_text_evidence_invalid")
    for item in value:
        _require(isinstance(item, dict)
                 and set(item) == {"kind", "sourceUrl", "sha256", "role"}
                 and item.get("kind") in {"official_subtitle", "official_transcript", "asr_transcript"}
                 and item.get("role") == "supplementary_only_not_audio_review"
                 and isinstance(item.get("sha256"), str) and _SHA256.fullmatch(item["sha256"]),
                 "official_video_text_evidence_invalid")
        try:
            _official_url(item.get("sourceUrl"))
        except OfficialResourceReviewError:
            raise OfficialResourceReviewError("official_video_text_evidence_invalid") from None


def _validate_video_modality_review(resource, *, reviewer, completed_at):
    record = resource.get("videoModalityReview")
    _require(isinstance(record, dict)
             and set(record) == {"schemaVersion", "visual", "audio"}
             and record.get("schemaVersion") == VIDEO_MODALITY_REVIEW_SCHEMA,
             "official_video_modality_review_required")
    visual = record.get("visual")
    visual_fields = {"status", "evidenceKind", "method", "reviewedAt", "reviewedBy",
                     "intervals", "findings"}
    _modality_common(visual, fields=visual_fields, reviewer=reviewer,
                     completed_at=completed_at, intervals_required=True,
                     code="official_video_visual_review_invalid")
    _require(visual.get("status") == "reviewed"
             and visual.get("evidenceKind") in {
                 "continuous_original_playback", "downloaded_original_video",
                 "human_verified_official_player",
             }, "official_video_visual_review_invalid")

    audio = record.get("audio")
    _require(isinstance(audio, dict), "official_video_audio_review_invalid")
    common = {"status", "sourceKind", "originalTrackRendered", "method", "reviewedAt",
              "reviewedBy", "intervals", "findings", "supportingTextEvidence"}
    status = audio.get("status")
    if status == "reviewed":
        fields = common | {"evidenceKind"}
        _modality_common(audio, fields=fields, reviewer=reviewer,
                         completed_at=completed_at, intervals_required=True,
                         code="official_video_audio_review_invalid")
        _supporting_text_evidence(audio.get("supportingTextEvidence"))
        note = "\n".join([audio["method"], *audio["findings"]])
        _require(audio.get("sourceKind") == "original_video_audio_track"
                 and audio.get("originalTrackRendered") is True
                 and audio.get("evidenceKind") in {
                     "audible_original_playback", "audio_tool_output",
                     "human_verified_official_player",
                 }
                 and not _AUDIO_TEXT_ONLY.search(note) and not _AUDIO_NOT_HEARD.search(note),
                 "official_video_audio_original_track_unreviewed")
        return
    if status == "not_applicable":
        fields = common | {"officialAudioStreamCount", "metadataSourceUrl", "metadataSha256"}
        _modality_common(audio, fields=fields, reviewer=reviewer,
                         completed_at=completed_at, intervals_required=False,
                         code="official_video_no_audio_evidence_invalid")
        _supporting_text_evidence(audio.get("supportingTextEvidence"))
        try:
            _official_url(audio.get("metadataSourceUrl"))
        except OfficialResourceReviewError:
            raise OfficialResourceReviewError("official_video_no_audio_evidence_invalid") from None
        note = "\n".join([audio["method"], *audio["findings"]])
        _require(audio.get("sourceKind") == "official_metadata_no_audio_track"
                 and audio.get("originalTrackRendered") is False
                 and type(audio.get("officialAudioStreamCount")) is int
                 and audio.get("officialAudioStreamCount") == 0
                 and isinstance(audio.get("metadataSha256"), str)
                 and _SHA256.fullmatch(audio["metadataSha256"])
                 and not _AUDIO_ACCESS_BLOCKED.search(note),
                 "official_video_no_audio_evidence_invalid")
        return
    raise OfficialResourceReviewError("official_video_audio_review_invalid")


def _discloses_incomplete_review(findings):
    for finding in findings:
        for clause in re.split(r"[，,。；;\n！？!?]", finding):
            clause = clause.strip()
            if any(pattern.search(clause) for pattern in
                   (_UNREAD_DISCLOSURE, _TITLE_ONLY_DISCLOSURE, _ACCESS_DISCLOSURE)):
                return True
    return False


def _review_exceptions(review, binding, hours):
    """Validate recorded per-draft authorization, not infer human permission."""
    records = review.get("reviewExceptions", [])
    _require(isinstance(records, list), "official_resource_exceptions_invalid")
    hour_ids = {hour.get("classHourId") for hour in hours if isinstance(hour, dict)
                and isinstance(hour.get("classHourId"), str)}
    result = {}
    for record in records:
        _require(isinstance(record, dict)
                 and record.get("resourceType") in WAIVABLE_UNAVAILABLE_RESOURCES,
                 "official_resource_exception_type_invalid")
        scoped_binding = record.get("binding")
        _require(isinstance(scoped_binding, dict)
                 and all(scoped_binding.get(key) == binding[key] for key in BINDING_FIELDS),
                 "official_resource_exception_binding_mismatch")
        for key in ("unitId", "unitTitle", "lessonTitle"):
            if key in scoped_binding:
                _require(scoped_binding[key] == binding.get(key),
                         "official_resource_exception_binding_mismatch")
        _require(record.get("authorizedBy") == "user"
                 and _text(record.get("userInstruction")) and _text(record.get("reason")),
                 "official_resource_exception_authorization_missing")
        try:
            authorized_at = datetime.fromisoformat(record.get("authorizedAt", "").replace("Z", "+00:00"))
            _require(authorized_at.tzinfo is not None, "official_resource_exception_date_invalid")
        except OfficialResourceReviewError:
            raise
        except (TypeError, ValueError, AttributeError):
            raise OfficialResourceReviewError("official_resource_exception_date_invalid") from None
        scoped_hours = record.get("classHourIds")
        _require(isinstance(scoped_hours, list) and bool(scoped_hours)
                 and all(isinstance(hour, str) and hour in hour_ids for hour in scoped_hours)
                 and len(scoped_hours) == len(set(scoped_hours)),
                 "official_resource_exception_hours_invalid")
        for hour_id in scoped_hours:
            key = (hour_id, record["resourceType"])
            _require(key not in result, "official_resource_exception_duplicate")
            result[key] = record
    return result


def _official_url(value):
    _require(_text(value) and value == value.strip(), "official_resource_url_invalid")
    try:
        parsed = urlsplit(value)
        host = str(parsed.hostname or "").lower()
        valid = (
            parsed.scheme == "https" and not parsed.username and not parsed.password
            and parsed.port in {None, 443} and not parsed.fragment
            and (host == "smartedu.cn" or host.endswith(".smartedu.cn")
                 or host == "cbern.com.cn" or host.endswith(".cbern.com.cn"))
            and not any(ord(char) < 32 or ord(char) == 127 for char in value)
        )
        query = parse_qs(parsed.query, keep_blank_values=True)
    except ValueError:
        valid, query = False, {}
    _require(valid and not any(_AUTH_QUERY.search(key) for key in query),
             "official_resource_url_invalid")
    return parsed, query


def _course_url(value, class_hour_id, teaching_material_id, *, legacy_identity=None, binding=None):
    parsed, query = _official_url(value)
    _require(parsed.hostname == "basic.smartedu.cn", "official_course_url_invalid")
    if parsed.path == "/syncClassroom/classActivity":
        _require(legacy_identity is None, "official_legacy_course_identity_unexpected")
        keys = ("teachingmaterialId", "chapterId", "activityId", "classHourId")
        _require(all(len(query.get(key, [])) == 1 and _ID.fullmatch(query[key][0]) for key in keys),
                 "official_course_identity_missing")
        _require(query["classHourId"][0] == class_hour_id
                 and query["teachingmaterialId"][0] == teaching_material_id,
                 "official_course_identity_mismatch")
        return parsed, query, "class_activity"
    _require(parsed.path == "/syncClassroom/prepare/detail", "official_course_url_invalid")
    keys = ("lessonId", "classHourId")
    _require(set(query) == set(keys)
             and all(len(query.get(key, [])) == 1 and _ID.fullmatch(query[key][0]) for key in keys),
             "official_legacy_course_identity_missing")
    _require(query["classHourId"][0] == class_hour_id,
             "official_course_identity_mismatch")
    _require(isinstance(binding, dict) and isinstance(legacy_identity, dict)
             and set(legacy_identity) == {
                 "schemaVersion", "lessonId", "classHourId", "teachingMaterialId",
                 "editionId", "revisionId", "nodeId", "evidenceLocations",
             }
             and legacy_identity.get("schemaVersion") == LEGACY_COURSE_IDENTITY_SCHEMA
             and legacy_identity.get("lessonId") == query["lessonId"][0]
             and legacy_identity.get("classHourId") == class_hour_id
             and legacy_identity.get("teachingMaterialId") == teaching_material_id
             and all(legacy_identity.get(key) == binding.get(key)
                     for key in ("editionId", "revisionId", "nodeId"))
             and _texts(legacy_identity.get("evidenceLocations")),
             "official_legacy_course_identity_mismatch")
    return parsed, query, "prepare_detail"


def validate_official_resource_review(review, binding):
    """Check the declared identity, five resources per hour and original plan.

    URLs refer to the public activity or an official resource domain. Signed or
    credential-bearing links are rejected; use the public activity URL and a
    precise page/time/list location when a viewer uses private media requests.
    """
    _require(isinstance(review, dict) and review.get("schemaVersion") == SCHEMA,
             "official_resource_review_required")
    reviewed_binding = review.get("binding")
    _require(isinstance(binding, dict) and isinstance(reviewed_binding, dict)
             and all(_text(binding.get(key)) and reviewed_binding.get(key) == binding[key]
                     for key in BINDING_FIELDS), "official_textbook_binding_mismatch")
    for key in ("unitId", "unitTitle", "lessonTitle"):
        if key in reviewed_binding:
            _require(reviewed_binding[key] == binding.get(key), "official_textbook_binding_mismatch")
    if "title" in reviewed_binding:
        _require(reviewed_binding["title"] == binding.get("lessonTitle"),
                 "official_textbook_binding_mismatch")
    book = review.get("officialTextbook")
    _require(isinstance(book, dict)
             and all(_text(book.get(key)) for key in
                     ("title", "publisher", "editionLabel", "publicationDate",
                      "teachingMaterialId", "editionMatchEvidence")),
             "official_textbook_identity_incomplete")
    _require(all(book.get(key) == binding[key] for key in ("gradeCode", "subject", "volume"))
             and _ID.fullmatch(book["teachingMaterialId"]), "official_textbook_identity_mismatch")
    try:
        publication = book["publicationDate"]
        _require(bool(re.fullmatch(r"\d{4}-\d{2}(?:-\d{2})?", publication)),
                 "official_textbook_publication_date_invalid")
        date.fromisoformat(publication + "-01" if len(publication) == 7 else publication)
        reviewed_at = datetime.fromisoformat(review.get("reviewedAt", "").replace("Z", "+00:00"))
        _require(reviewed_at.tzinfo is not None and _text(review.get("reviewedBy")),
                 "official_resource_reviewer_missing")
    except OfficialResourceReviewError:
        raise
    except (TypeError, ValueError, AttributeError):
        raise OfficialResourceReviewError("official_resource_review_date_invalid") from None
    hours = review.get("classHours")
    _require(isinstance(hours, list) and bool(hours), "official_class_hours_missing")
    exceptions = _review_exceptions(review, binding, hours)
    used_exceptions = set()
    seen = set()
    for hour in hours:
        _require(isinstance(hour, dict) and _text(hour.get("classHourId"))
                 and _ID.fullmatch(hour["classHourId"]) and hour["classHourId"] not in seen
                 and _text(hour.get("title")) and _texts(hour.get("learningObjectives")),
                 "official_class_hour_invalid")
        seen.add(hour["classHourId"])
        course_url, course_query, course_kind = _course_url(
            hour.get("courseUrl"), hour["classHourId"], book["teachingMaterialId"],
            legacy_identity=hour.get("legacyCourseIdentity"), binding=binding,
        )
        resources = hour.get("resources")
        _require(isinstance(resources, dict) and set(resources) == set(REQUIRED_RESOURCES),
                 "official_resources_incomplete")
        if any(isinstance(resource, dict) and resource.get("status") == "waived_unavailable"
               for resource in resources.values()):
            _require(all(isinstance(resources[kind], dict)
                         and resources[kind].get("status") in {"reviewed", "not_provided"}
                         for kind in UNWAIVABLE_RESOURCES), "official_unwaivable_resource_unreviewed")
        for kind in REQUIRED_RESOURCES:
            resource = resources[kind]
            _require(isinstance(resource, dict)
                     and (resource.get("status") in {"reviewed", "not_provided"}
                          or (resource.get("status") == "waived_unavailable"
                              and (hour["classHourId"], kind) in exceptions)),
                     "official_resource_unreviewed")
            resource_url, resource_query = _official_url(resource.get("sourceUrl"))
            if resource_url.hostname == "basic.smartedu.cn" and resource_url.path in {
                    "/syncClassroom/classActivity", "/syncClassroom/prepare/detail"}:
                if resource_url.path == "/syncClassroom/classActivity":
                    matches = (course_kind == "class_activity"
                               and all(resource_query.get(key) == course_query[key] for key in
                                       ("teachingmaterialId", "chapterId", "activityId", "classHourId")))
                else:
                    matches = (course_kind == "prepare_detail" and resource_query == course_query
                               and resource_url.path == course_url.path)
                _require(matches, "official_resource_class_hour_mismatch")
            _require(_texts(resource.get("locations")) and _texts(resource.get("findings")),
                     "official_resource_findings_missing")
            if resource["status"] == "reviewed":
                _require(not _discloses_incomplete_review(resource["findings"]),
                         "official_resource_unreviewed")
                if kind == "video":
                    _validate_video_modality_review(
                        resource, reviewer=review["reviewedBy"], completed_at=reviewed_at,
                    )
            elif kind == "video" and "videoModalityReview" in resource:
                _require(False, "official_video_modality_review_invalid_for_status")
            if resource["status"] == "waived_unavailable":
                _require(resource["sourceUrl"] == hour["courseUrl"],
                         "official_resource_exception_source_invalid")
                used_exceptions.add((hour["classHourId"], kind))
            if resource["status"] == "not_provided":
                note = "\n".join(resource["locations"] + resource["findings"])
                _require(resource["sourceUrl"] == hour["courseUrl"]
                         and _ABSENCE_NOTE.search(note) and _OFFICIAL_NOTE.search(note)
                         and not _BLOCKED_NOTE.search(note), "official_resource_absence_unverified")
    _require(used_exceptions == set(exceptions), "official_resource_exception_scope_unused")
    adaptation = review.get("adaptation")
    _require(isinstance(adaptation, dict)
             and all(_texts(adaptation.get(key)) for key in
                     ("preservedObjectives", "originalApproach", "differencesFromReference", "evidenceBoundaries")),
             "official_resource_adaptation_missing")
    return review


def validate_draft_official_resource_review(draft):
    scope = draft.get("scopeReview") if isinstance(draft, dict) else None
    return validate_official_resource_review(
        scope.get("officialResourceReview") if isinstance(scope, dict) else None,
        draft.get("binding") if isinstance(draft, dict) else None,
    )


def validate_new_course_post_class_practice(draft, review=None):
    """Require a source-bound, original in-course use for new authoring only.

    Historical frozen jobs do not call this function.  The weekend pack remains
    a later reviewed artifact; this mapping only proves that at least one
    official after-class goal has an intentional place in the course itself.
    A real official inventory absence is recorded as a shortage, never padded
    into a fictional goal or mapping.
    """
    scope = draft.get("scopeReview") if isinstance(draft, dict) else None
    practice = scope.get("postClassPractice") if isinstance(scope, dict) else None
    _require(isinstance(practice, dict)
             and practice.get("schemaVersion") == POST_CLASS_PRACTICE_SCHEMA,
             "post_class_practice_required")
    if review is None:
        review = validate_draft_official_resource_review(draft)
    _require(practice.get("officialResourceReviewSha256") == digest(review),
             "post_class_practice_review_mismatch")
    _require(_text(practice.get("sourceKind")) and _text(practice.get("sourceContract"))
             and isinstance(practice.get("originalFileDownloaded"), bool)
             and isinstance(practice.get("sourceSha256"), str)
             and bool(re.fullmatch(r"[0-9a-f]{64}", practice["sourceSha256"])),
             "post_class_practice_source_invalid")
    target_seconds = practice.get("targetSeconds")
    goals = practice.get("goals")
    mappings = practice.get("inCoursePractice")
    hours = {hour["classHourId"]: hour for hour in review["classHours"]}
    absent_hours = [hour for hour in review["classHours"]
                    if hour["resources"]["afterClassExercise"]["status"] == "not_provided"]
    shortage = practice.get("officialGoalShortage")
    if absent_hours:
        expected_locations = list(dict.fromkeys(
            location for hour in absent_hours
            for location in hour["resources"]["afterClassExercise"]["locations"]
        ))
        _require(isinstance(shortage, dict)
                 and set(shortage) == {"status", "classHourIds", "sourceLocations", "handling"}
                 and shortage.get("status") == "official_after_class_exercise_not_provided"
                 and shortage.get("classHourIds") == [hour["classHourId"] for hour in absent_hours]
                 and shortage.get("sourceLocations") == expected_locations
                 and _texts(shortage.get("handling")),
                 "post_class_official_goal_shortage_invalid")
    else:
        _require(shortage is None, "post_class_official_goal_shortage_unexpected")
    if len(absent_hours) == len(review["classHours"]):
        _require(target_seconds == 0 and goals == [] and mappings == []
                 and practice.get("sourceKind") == "official-inventory-absence"
                 and practice.get("originalFileDownloaded") is False,
                 "post_class_official_goal_shortage_invalid")
        return practice
    _require(type(target_seconds) is int and 1 <= target_seconds <= 4 * 60 * 60,
             "post_class_practice_duration_invalid")
    _require(isinstance(goals, list) and bool(goals)
             and all(isinstance(goal, str) and _ID.fullmatch(goal) for goal in goals)
             and len(goals) == len(set(goals)), "post_class_practice_goals_invalid")
    pages = {page.get("page"): page for page in draft.get("pagePlan", [])
             if isinstance(page, dict) and type(page.get("page")) is int}
    _require(isinstance(mappings, list) and bool(mappings),
             "post_class_in_course_mapping_required")
    seen = set()
    for mapping in mappings:
        _require(isinstance(mapping, dict)
                 and isinstance(mapping.get("activityId"), str)
                 and _ID.fullmatch(mapping["activityId"])
                 and mapping["activityId"] not in seen
                 and mapping.get("goalId") in goals
                 and mapping.get("classHourId") in hours
                 and hours[mapping["classHourId"]]["resources"]["afterClassExercise"]["status"] == "reviewed"
                 and type(mapping.get("page")) is int and mapping["page"] in pages
                 and _text(mapping.get("originalDesign"))
                 and _text(mapping.get("evidenceClaim")),
                 "post_class_in_course_mapping_invalid")
        seen.add(mapping["activityId"])
        locations = mapping.get("sourceLocations")
        source_locations = hours[mapping["classHourId"]]["resources"]["afterClassExercise"]["locations"]
        _require(_texts(locations) and all(location in source_locations for location in locations),
                 "post_class_in_course_source_mismatch")
    return practice
