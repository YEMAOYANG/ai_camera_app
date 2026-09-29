from __future__ import annotations

from datetime import datetime
import json
import re
from zoneinfo import ZoneInfo

from content.textbook_catalog import (SUBJECTS, authoring_prompt, digest, fields, generation_brief,
                                      identifier, lesson_by_id, superseded_resources, text, validate_frozen_brief, validate_manifest)
from content.textbook_metadata import reviewed_edition_label
from core.errors import ApiError
from core.security import now_ms
from content.textbook_introductions import public_introduction
from services.textbook_journey_service import catalog_journeys

RESPONSE_SCHEMA = "mira.learning.textbooks.v1"


def school_term(today=None):
    today = today or datetime.now(ZoneInfo("Asia/Shanghai"))
    return today.year if today.month >= 9 else today.year - 1, "upper" if today.month >= 9 or today.month == 1 else "lower"


def textbook_context(repository, conn, child):
    """One effective term for catalogue, selections and every classroom gate.

    The date is a suggestion, not a claim about a school's holiday calendar.
    A parent's override expires with the academic year or confirmed grade.
    """
    year, suggested = school_term()
    saved = repository.learning_context(conn, child)
    applicable = (saved.get("schoolYearStartYear") == year
                  and saved.get("gradeRevision") == child["grade_selection_revision"])
    manual = saved.get("semester") if applicable else None
    return {"schoolYearStartYear": year, "semester": manual or suggested,
            "suggestedSemester": suggested, "termSource": "parent" if manual else "calendar",
            "contextRevision": saved.get("revision", 0), "gradeRevision": int(child["grade_selection_revision"])}


class TextbookLearningService:
    def __init__(self, repository, *, student_auth_service=None, profile_service=None, student_learning_service=None):
        self.repository = repository
        self.student_auth_service = student_auth_service
        self.profile_service = profile_service
        self.student_learning_service = student_learning_service

    def import_manifest(self, data):
        manifest = validate_manifest(data)
        with self.repository.transaction() as conn:
            row, created = self.repository.import_revision(conn, manifest, now_ms())
        return {"ok": True, "created": created, "editionId": row["edition_id"],
                "revisionId": row["revision_id"], "manifestSha256": row["manifest_sha256"]}

    def import_catalog(self, data):
        """Explicit CLI bulk import is atomic, including immutable revision conflicts."""
        if not isinstance(data, list) or not 1 <= len(data) <= 500:
            raise ApiError("textbook_catalog_invalid", "教材目录文件数量无效", 400)
        manifests = [validate_manifest(item) for item in data]
        identities = {(m["editionId"], m["revisionId"]) for m in manifests}
        if len(identities) != len(manifests):
            raise ApiError("textbook_catalog_invalid", "目录包含重复的教材修订", 400)
        results = []
        with self.repository.transaction() as conn:
            for manifest in sorted(manifests, key=lambda m: (m["editionId"], m["revisionId"])):
                row, created = self.repository.import_revision(conn, manifest, now_ms())
                results.append({"editionId": row["edition_id"], "revisionId": row["revision_id"], "created": created})
        return {"ok": True, "books": results, "providerDispatched": False}

    def _student(self, token):
        context = self.student_auth_service.authenticate(token)
        with self.repository.transaction() as conn:
            child = self.repository.child(conn, context["principal"]["family_id"], context["principal"]["child_id"])
        if child is None:
            raise ApiError("textbook_child_not_found", "学习身份已变更，请重新登录", 404)
        return child

    @staticmethod
    def _query(query, allowed=()):
        if (set(query or {}) - set(allowed)
                or hasattr(query, "lists") and any(len(values) != 1 for _, values in query.lists())):
            raise ApiError("textbook_query_invalid", "教材查询参数无效", 400)

    def student_catalog(self, token, query):
        self._query(query)
        catalog = self.catalog(self._student(token))
        # Parents choose editions. Children choose subjects, never an arbitrary
        # regional/system variant from the operator's complete catalogue.
        catalog["books"] = [book for book in catalog["books"] if book["selected"]]
        return catalog

    def catalog(self, child):
        with self.repository.transaction() as conn:
            context = textbook_context(self.repository, conn, child)
            year, semester = context["schoolYearStartYear"], context["semester"]
            rows = self.repository.list_revisions(conn, child["grade_code"])
            choices = self.repository.selections(conn, child, year, semester)
        selected = {(r["edition_id"], r["revision_id"]): r for r in choices}
        subject_revisions = {r["subject"]: int(r["selection_revision"]) for r in choices}
        # A metadata correction is another revision of the same school book,
        # not a second book in the picker. Preserve a parent's pinned revision;
        # otherwise show the latest imported revision without rewriting history.
        displayed = {}
        for row in rows:
            previous = displayed.get(row["edition_id"])
            priority = lambda r: ((r["edition_id"], r["revision_id"]) in selected,
                                  r["imported_at"], r["revision_id"])
            if previous is None or priority(row) > priority(previous):
                displayed[row["edition_id"]] = row
        books = []
        for row in displayed.values():
            m = self.repository.manifest(row)
            choice = selected.get((row["edition_id"], row["revision_id"]))
            if not choice and m["source"]["resourceId"] in superseded_resources():
                continue
            books.append({**self._book(m), "selected": choice is not None,
                          "selectionRevision": subject_revisions.get(m["subject"], 0),
                          "currentNodeId": choice["current_node_id"] if choice else None})
        books.sort(key=lambda b: (not b["selected"], b["volume"] not in {semester, "full"},
                                  b["schoolSystem"] != "six_year", b["subject"], b["editionId"], b["revisionId"]))
        with self.repository.transaction() as conn:
            completed = None
            visible_courses = set()
            for book in books:
                if not book["selected"]:
                    continue
                manifest = self._revision(conn, child, book["editionId"], book["revisionId"])
                builds = self.repository.builds(conn, book["editionId"], book["revisionId"])
                available, locked = [], 0
                for unit in manifest["units"]:
                    for node in unit["lessons"]:
                        course, blocked = self._available_course(conn, child, manifest, node, builds)
                        if course:
                            available.append((course["courseId"], course["courseVersion"]))
                        elif blocked:
                            locked += 1
                visible_courses.update(available)
                if available and completed is None:
                    completed = self.repository.completed_courses(conn, child)
                book["learningStatus"] = {
                    "status": "ready" if available else "locked" if locked else "unpublished",
                    "availableLessonCount": len(available),
                    "completedLessonCount": sum(key in (completed or set()) for key in available),
                }
        with self.repository.transaction() as conn:
            journeys = catalog_journeys(self.repository, conn, child, books, visible_courses)
        subjects = []
        for subject in SUBJECTS:
            selected_book = next((b for b in books if b["subject"] == subject and b["selected"]), None)
            offered = any(b["subject"] == subject and b["volume"] in {semester, "full"} for b in books)
            subjects.append({"subject": subject, "status": "confirmed" if selected_book else "selection_required" if offered else "unavailable"})
        return {"ok": True, "schemaVersion": RESPONSE_SCHEMA, "gradeCode": child["grade_code"],
                **context, "subjects": subjects, "books": books, "learningJourneys": journeys}

    @staticmethod
    def _book(manifest):
        return {**{k: manifest[k] for k in ("editionId", "revisionId", "title", "publisher", "editionLabel",
                                            "gradeCode", "subject", "volume", "schoolSystem", "coverage")},
                "editionLabel": reviewed_edition_label(manifest),
                "sourceUrl": manifest["source"]["url"],
                "unitCount": len(manifest["units"]),
                "lessonCount": sum(len(u["lessons"]) for u in manifest["units"])}

    def _revision(self, conn, child, edition_id, revision_id):
        if not identifier(edition_id) or not identifier(revision_id):
            raise ApiError("textbook_not_found", "教材不存在", 404)
        row = self.repository.get_revision(conn, edition_id, revision_id)
        if row is None or row["grade_code"] != child["grade_code"]:
            raise ApiError("textbook_not_found", "没有找到当前年级的这本教材", 404)
        manifest = self.repository.manifest(row)
        if digest(manifest) != row["manifest_sha256"]:
            raise ApiError("textbook_integrity_error", "教材资料正在核对，请稍后再来", 409)
        return manifest

    def student_contents(self, token, edition_id, query):
        self._query(query, ("alignmentRevisionId",))
        child = self._student(token)
        revision_id = (query or {}).get("alignmentRevisionId")
        with self.repository.transaction() as conn:
            context = textbook_context(self.repository, conn, child)
            year, semester = context["schoolYearStartYear"], context["semester"]
            manifest = self._revision(conn, child, edition_id, revision_id)
            choices = self.repository.selections(conn, child, year, semester)
            selection = next((r for r in choices if r["edition_id"] == edition_id and r["revision_id"] == revision_id), None)
            if selection is None:
                raise ApiError("textbook_selection_required", "请家长在 App 的“学校教材”中确认这学期的课本，再回到书包刷新。", 409)
            builds = self.repository.builds(conn, edition_id, revision_id)
            units = []
            for unit in manifest["units"]:
                lessons = []
                for node in unit["lessons"]:
                    # A published binding is never sufficient on its own. Existing
                    # student visibility/media/identity gates remain authoritative.
                    course, blocked = self._available_course(conn, child, manifest, node, builds) if selection else (None, None)
                    reviewed = manifest["rightsReview"]["status"] == "cleared" and node["brief"]["status"] == "approved"
                    status = "ready" if course else "locked" if blocked else "preparing" if reviewed else "reviewing"
                    lessons.append({"nodeId": node["nodeId"], "title": node["title"], "sequence": node["sequence"],
                                    **({"sectionTitle": node["sectionTitle"]} if node.get("sectionTitle") else {}),
                                    "printedPage": node["printedPage"], "pdfPage": node["pdfPage"],
                                    "objectives": node["brief"]["objectives"], "status": status, "message": blocked, "course": course})
                units.append({"unitId": unit["unitId"], "title": unit["title"], "sequence": unit["sequence"],
                              "kind": unit.get("kind", "unit"),
                              "introduction": public_introduction(unit.get("introduction"), manifest=manifest), "lessons": lessons})
        return {"ok": True, "schemaVersion": RESPONSE_SCHEMA, "book": self._book(manifest),
                "selected": selection is not None, "selectionRevision": int(selection["selection_revision"]) if selection else 0,
                "currentNodeId": selection["current_node_id"] if selection else None,
                "introduction": public_introduction(manifest.get("introduction"), manifest=manifest), "units": units}

    def _available_course(self, conn, child, manifest, node, builds):
        # Saved-artifact releases have a per-lesson review and immutable media
        # audit. They do not upgrade the pending review of the entire book.
        from content.textbook_release import INPUT_SCHEMA, validate_release
        candidates = [b for b in builds if b['node_id'] == node['nodeId'] and b['part_index'] == 1]
        if candidates:
            build = candidates[0]
            if self.repository.parse(build['input_json']).get('schemaVersion') == INPUT_SCHEMA:
                course = conn.execute('SELECT * FROM learning_courses WHERE id=? AND version=?',
                                      (build['course_id'], build['course_version'])).fetchone()
                try:
                    if course is not None and validate_release(build, manifest, course):
                        return {'courseId': course['id'], 'courseVersion': course['version'],
                                'contentKey': build['content_key'], 'delivery': 'fixed_textbook'}, None
                except ApiError:
                    pass
                return None, None
        if manifest["rightsReview"]["status"] != "cleared" or node["brief"]["status"] != "approved" or self.student_learning_service is None:
            return None, None
        blocked = None
        # Pick the shared published revision before checking personal access.
        # Never fall back to different courseware for different students.
        for build in candidates[:1]:
            course = self.student_learning_service.repository.get_student_visible_course(
                conn, family_id=child["family_id"], child_id=child["id"], grade_code=child["grade_code"],
                grade_selection_revision=int(child["grade_selection_revision"]),
                course_id=build["course_id"], course_version=build["course_version"])
            if course is None:
                continue
            try:
                content = self.repository.parse(course["content_json"])
                expected = validate_frozen_brief(manifest, self.repository.parse(build["input_json"]))
            except (ApiError, ValueError, TypeError):
                continue
            if (not isinstance(content, dict) or digest(content) != build["course_content_sha256"] or expected["contentKey"] != build["content_key"]
                    or content.get("textbookBinding") != expected["textbookBinding"]):
                continue
            # Reuse the same progression check as the locked start/session path.
            try:
                self.student_learning_service.learning_service.assert_course_progression(conn, child=child, course=course)
            except ApiError as exc:
                if exc.code == "learning_prerequisite_not_mastered":
                    blocked = exc.message
                continue
            return {"courseId": course["id"], "courseVersion": course["version"], "contentKey": build["content_key"]}, None
        return None, blocked

    def parent_catalog(self, token, child_id):
        profile = self.profile_service
        context = profile._auth_context(token)
        with self.repository.transaction() as conn:
            profile._assert_capability(conn, context, "manage_child_profile")
            child = self.repository.child(conn, context["family"]["id"], child_id)
            if child is None:
                raise ApiError("child_not_found", "没有找到孩子", 404)
        return self.catalog(child)

    def parent_select(self, token, child_id, data):
        fields(data, ("editionId", "alignmentRevisionId", "expectedSelectionRevision", "schoolYearStartYear", "semester"), ("currentNodeId",))
        result = self.parent_select_many(token, child_id, {
            "schoolYearStartYear": data["schoolYearStartYear"], "semester": data["semester"],
            "selections": [{k: v for k, v in data.items() if k not in {"schoolYearStartYear", "semester"}}],
        })
        return {"ok": True, **{k: v for k, v in result["selections"][0].items() if k != "subject"}}

    def parent_select_many(self, token, child_id, data):
        fields(data, ("schoolYearStartYear", "semester", "selections"), ("expectedContextRevision",))
        selections = data["selections"]
        if not isinstance(selections, list) or not 1 <= len(selections) <= len(SUBJECTS):
            raise ApiError("textbook_selection_invalid", "请选择需要确认的教材", 400)
        for selection in selections:
            fields(selection, ("editionId", "alignmentRevisionId", "expectedSelectionRevision"), ("currentNodeId",))
            if type(selection["expectedSelectionRevision"]) is not int or selection["expectedSelectionRevision"] < 0:
                raise ApiError("textbook_selection_invalid", "教材选择修订号无效", 400)
        profile = self.profile_service
        auth = profile._auth_context(token)
        with self.repository.transaction() as conn:
            profile.repository.lock_family(conn, family_id=auth["family"]["id"])
            profile._assert_capability(conn, auth, "manage_child_profile")
            child = self.repository.child(conn, auth["family"]["id"], child_id, lock=True)
            if child is None:
                raise ApiError("child_not_found", "没有找到孩子", 404)
            context = textbook_context(self.repository, conn, child)
            year, semester = context["schoolYearStartYear"], context["semester"]
            if (type(data["schoolYearStartYear"]) is not int
                    or (data["schoolYearStartYear"], data["semester"]) != (year, semester)
                    or ("expectedContextRevision" in data and (type(data["expectedContextRevision"]) is not int
                        or data["expectedContextRevision"] != context["contextRevision"]))):
                raise ApiError("textbook_term_changed", "学期或学科设置已变化，请刷新教材列表", 409)
            if not child.get("grade_selection_revision") or int(child["grade_selection_revision"]) < 1:
                raise ApiError("textbook_grade_unconfirmed", "请先在孩子资料中确认就读年级", 409)
            prepared, subjects = [], set()
            for selection in selections:
                manifest = self._revision(conn, child, selection["editionId"], selection["alignmentRevisionId"])
                if manifest["subject"] in subjects:
                    raise ApiError("textbook_selection_invalid", "每个学科只能确认一本教材", 400)
                subjects.add(manifest["subject"])
                if manifest["volume"] not in {semester, "full"}:
                    raise ApiError("textbook_volume_mismatch", "请选择本学期使用的册次", 409)
                node = selection.get("currentNodeId")
                if node is not None:
                    lesson_by_id(manifest, node)
                prepared.append((manifest, selection, node))
            result = []
            for manifest, selection, node in prepared:
                revision = self.repository.select(conn, child=child, manifest=manifest, year=year, semester=semester,
                                                 expected_revision=selection["expectedSelectionRevision"], current_node=node,
                                                 confirmed_by=auth["user"]["id"], now=now_ms())
                result.append({"subject": manifest["subject"], "selectionRevision": revision,
                               "editionId": manifest["editionId"], "alignmentRevisionId": manifest["revisionId"]})
        return {"ok": True, "selections": result}

    def parent_update_context(self, token, child_id, data):
        fields(data, ("schoolYearStartYear", "semester", "expectedContextRevision", "expectedGradeRevision"))
        if (data["semester"] not in (None, "upper", "lower")
                or any(type(data[k]) is not int for k in ("schoolYearStartYear", "expectedContextRevision", "expectedGradeRevision"))):
            raise ApiError("textbook_context_invalid", "学期或学科设置无效", 400)
        profile = self.profile_service
        auth = profile._auth_context(token)
        with self.repository.transaction() as conn:
            profile.repository.lock_family(conn, family_id=auth["family"]["id"])
            profile._assert_capability(conn, auth, "manage_child_profile")
            child = self.repository.child(conn, auth["family"]["id"], child_id, lock=True)
            if child is None:
                raise ApiError("child_not_found", "没有找到孩子", 404)
            current = textbook_context(self.repository, conn, child)
            if (data["schoolYearStartYear"] != current["schoolYearStartYear"]
                    or data["expectedContextRevision"] != current["contextRevision"]
                    or data["expectedGradeRevision"] != current["gradeRevision"]):
                raise ApiError("textbook_context_changed", "年级或学期设置已更新，请刷新后再修改", 409)
            if current["gradeRevision"] < 1 or not child["grade_code"].startswith("primary_"):
                raise ApiError("textbook_grade_unconfirmed", "请先确认小学年级", 409)
            self.repository.save_learning_context(conn, child, {
                "revision": current["contextRevision"] + 1, "gradeRevision": current["gradeRevision"],
                "schoolYearStartYear": current["schoolYearStartYear"], "semester": data["semester"],
                "confirmedBy": auth["user"]["id"],
            }, now_ms())
        return {"ok": True}

    def prepare(self, data):
        fields(data, ("editionId", "alignmentRevisionId", "nodeId"), ("teachingRevision", "partIndex"))
        if not all(identifier(data[k]) for k in ("editionId", "alignmentRevisionId", "nodeId")):
            raise ApiError("textbook_generation_invalid", "教材课次标识无效", 400)
        with self.repository.transaction() as conn:
            row = self.repository.get_revision(conn, data["editionId"], data["alignmentRevisionId"])
            if row is None:
                raise ApiError("textbook_not_found", "请先导入并核验教材", 404)
            manifest = self.repository.manifest(row)
            if digest(manifest) != row["manifest_sha256"]:
                raise ApiError("textbook_integrity_error", "教材资料摘要不一致", 409)
            brief = generation_brief(manifest, data["nodeId"], teaching_revision=data.get("teachingRevision", "1"), part_index=data.get("partIndex", 1))
            build, created = self.repository.reserve_build(conn, brief, now_ms())
        return {"ok": True, "created": created, "contentKey": build["content_key"], "status": build["status"],
                "generationInput": brief, "prompt": authoring_prompt(), "providerDispatched": False}

    def bind_published(self, data):
        """Attach reviewed output only after the existing full OpenMAIC release.

        This is an adapter boundary, not an alternative publication mechanism.
        Course JSON must have carried the exact textbook identity before release.
        """
        fields(data, ("contentKey", "courseId", "courseVersion", "courseContentSha256", "review"))
        for key in ("contentKey", "courseContentSha256"):
            if not isinstance(data[key], str) or re.fullmatch(r"[0-9a-f]{64}", data[key]) is None:
                raise ApiError("textbook_binding_invalid", "课程摘要无效", 400)
        text(data["courseId"], 255)
        text(data["courseVersion"], 64)
        review = data["review"]
        fields(review, ("reviewer", "reviewedAt", "alignmentConfirmed", "originalExpressionConfirmed", "sourceUsageConfirmed", "basis"))
        text(review["reviewer"], 120)
        text(review["basis"], 2000)
        if (type(review["reviewedAt"]) is not int or not 0 < review["reviewedAt"] <= now_ms()
                or any(review[k] is not True for k in ("alignmentConfirmed", "originalExpressionConfirmed", "sourceUsageConfirmed"))):
            raise ApiError("textbook_review_required", "需要记录教学对齐、原创表达及来源使用审核", 409)
        with self.repository.transaction() as conn:
            build = self.repository.get_build(conn, data["contentKey"], lock=True)
            if build is None:
                raise ApiError("textbook_build_not_found", "请先固定本课教学任务书", 404)
            row = self.repository.get_revision(conn, build["edition_id"], build["revision_id"])
            if row is None or digest(self.repository.manifest(row)) != row["manifest_sha256"]:
                raise ApiError("textbook_integrity_error", "教材修订已变化", 409)
            brief = validate_frozen_brief(self.repository.manifest(row), self.repository.parse(build["input_json"]))
            course = conn.execute("SELECT * FROM learning_courses WHERE id=? AND version=? AND status='published' AND quality_status='released' AND content_origin='openmaic_generated' AND retired_at IS NULL",
                                  (data["courseId"], data["courseVersion"])).fetchone()
            if course is None:
                raise ApiError("textbook_course_unavailable", "课程须先通过正式课堂发布检查", 409)
            content = self.repository.parse(course["content_json"])
            if (course["grade_code"] != brief["gradeCode"] or course["subject"] != brief["subject"]
                    or not isinstance(content, dict) or content.get("textbookBinding") != brief["textbookBinding"]
                    or digest(content) != data["courseContentSha256"]):
                raise ApiError("textbook_binding_invalid", "禁止把其他课程重贴标签作为教材课", 409)
            self._assert_published_supply(conn, course)
            changed = self.repository.bind_published(conn, build, course, review, now_ms())
        return {"ok": True, "created": changed, "contentKey": data["contentKey"], "status": "published"}

    @staticmethod
    def _assert_published_supply(conn, course):
        from repositories.course_supply_inventory import published_supply
        rows = conn.execute("SELECT DISTINCT build.target_spec_json FROM learning_catalog_build_jobs AS build JOIN learning_catalog_build_items AS item ON item.build_job_id=build.id WHERE item.course_id=? AND item.course_version=?",
                            (course["id"], course["version"])).fetchall()
        for row in rows:
            target = TextbookLearningService._parse_target(row["target_spec_json"])
            if target and any(r["course_id"] == course["id"] and r["course_version"] == course["version"] for r in published_supply(conn, target).values()):
                return
        raise ApiError("textbook_course_unavailable", "课件、语音或正式课堂发布尚未就绪", 409)

    @staticmethod
    def _parse_target(value):
        parsed = json.loads(value) if isinstance(value, str) else value
        return parsed if isinstance(parsed, dict) else None
