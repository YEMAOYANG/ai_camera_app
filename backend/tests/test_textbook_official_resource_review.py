"""Official-source input checks use synthetic records, never accounts/providers."""
from copy import deepcopy
import unittest

from content.textbook_official_resource_review import (
    BINDING_FIELDS, LEGACY_COURSE_IDENTITY_SCHEMA, OfficialResourceReviewError, POST_CLASS_PRACTICE_SCHEMA,
    REQUIRED_RESOURCES, SCHEMA, VIDEO_MODALITY_REVIEW_SCHEMA, validate_new_course_post_class_practice,
    validate_official_resource_review,
)
from content.textbook_catalog import digest


def reviewed_official_resources(binding):
    """Synthetic complete input, not evidence that a real course was reviewed."""
    url = ("https://basic.smartedu.cn/syncClassroom/classActivity?activityId=activity-one"
           "&chapterId=chapter-one&teachingmaterialId=material-one&classHourId=lesson_1")
    review = {
        "schemaVersion": SCHEMA,
        "binding": {key: binding[key] for key in BINDING_FIELDS},
        "officialTextbook": {
            "title": "测试教材", "publisher": "测试出版社", "editionLabel": "测试版",
            "publicationDate": "2024-08", "teachingMaterialId": "material-one",
            **{key: binding[key] for key in ("gradeCode", "subject", "volume")},
            "editionMatchEvidence": "测试审阅记录逐项核对教材、版次、年级、学科和册次；非真实来源证明。",
        },
        "reviewedAt": "2026-10-26T08:00:00+08:00", "reviewedBy": "fixture-reviewer",
        "classHours": [{
            "classHourId": "lesson_1", "title": "测试第一课时", "courseUrl": url,
            "learningObjectives": ["观察当前教材内的对象和关系。"],
            "resources": {kind: {
                "status": "reviewed", "sourceUrl": url,
                "locations": ["测试视频00:00–00:30或文档第1页；合成测试记录"],
                "findings": ["本课时先观察对象，再比较条件，最后尝试修改。"],
            } for kind in REQUIRED_RESOURCES},
        }],
        "adaptation": {
            "preservedObjectives": ["保留对象与关系的教材目标。"],
            "originalApproach": ["使用原创人物与可修改的场景。"],
            "differencesFromReference": ["将集体问答改成一屏一任务的图像操作。"],
            "evidenceBoundaries": ["结构完整不证明实际看过资源或儿童已经掌握。"],
        },
    }
    review["classHours"][0]["resources"]["video"]["videoModalityReview"] = {
        "schemaVersion": VIDEO_MODALITY_REVIEW_SCHEMA,
        "visual": {
            "status": "reviewed", "evidenceKind": "continuous_original_playback",
            "method": "合成测试连续查看原视频画面；不代表真实课程审阅。",
            "reviewedAt": review["reviewedAt"], "reviewedBy": review["reviewedBy"],
            "intervals": [{"start": "00:00", "end": "00:30"}],
            "findings": ["合成测试画面包含对象观察与条件比较。"],
        },
        "audio": {
            "status": "reviewed", "sourceKind": "original_video_audio_track",
            "originalTrackRendered": True, "evidenceKind": "audio_tool_output",
            "method": "合成测试通过音频工具输出实际听取原视频音轨；不代表真实课程审阅。",
            "reviewedAt": review["reviewedAt"], "reviewedBy": review["reviewedBy"],
            "intervals": [{"start": "00:00", "end": "00:30"}],
            "findings": ["合成测试音轨包含与画面目标相符的教师讲解。"],
            "supportingTextEvidence": [],
        },
    }
    return review


class OfficialResourceReviewTest(unittest.TestCase):
    def setUp(self):
        self.binding = {
            "editionId": "edition-one", "revisionId": "revision-one", "nodeId": "lesson-one",
            "gradeCode": "primary_1", "subject": "chinese", "volume": "upper",
            "schoolSystem": "six_year",
        }
        self.review = reviewed_official_resources(self.binding)

    def invalid(self, review, code=None):
        with self.assertRaises(OfficialResourceReviewError) as caught:
            validate_official_resource_review(review, self.binding)
        if code:
            self.assertEqual(str(caught.exception), code)

    def media_waiver(self):
        review = deepcopy(self.review)
        hour = review["classHours"][0]
        review["reviewExceptions"] = []
        for kind in ("video", "courseware"):
            if kind == "video":
                hour["resources"][kind].pop("videoModalityReview")
            hour["resources"][kind].update(
                status="waived_unavailable", locations=["本次官方课时资源获取检查"],
                findings=["本次无法取得该资源，依用户明确授权参考其余三项已阅材料制作。"],
            )
            review["reviewExceptions"].append({
                "resourceType": kind, "binding": deepcopy(review["binding"]),
                "classHourIds": [hour["classHourId"]], "authorizedBy": "user",
                "authorizedAt": "2026-10-26T17:00:00+08:00",
                "userInstruction": "视频课程和课件没有就算了，你就根据其他三项内容，重新开始生成课件和发布。",
                "reason": "本次该资源无法取得；仅依该课已读教学设计、学习任务单、课后练习制作。",
            })
        return review

    def legacy_prepare_review(self):
        review = deepcopy(self.review)
        url = ("https://basic.smartedu.cn/syncClassroom/prepare/detail?"
               "lessonId=legacy-lesson-one&classHourId=lesson_1")
        hour = review["classHours"][0]
        hour["courseUrl"] = url
        for resource in hour["resources"].values():
            resource["sourceUrl"] = url
        hour["legacyCourseIdentity"] = {
            "schemaVersion": LEGACY_COURSE_IDENTITY_SCHEMA,
            "lessonId": "legacy-lesson-one", "classHourId": "lesson_1",
            "teachingMaterialId": review["officialTextbook"]["teachingMaterialId"],
            "editionId": self.binding["editionId"], "revisionId": self.binding["revisionId"],
            "nodeId": self.binding["nodeId"],
            "evidenceLocations": [
                "国家平台旧版备课页教材面包屑与本目录节点一致。",
                "公开教材目录中的版次、册次与当前节点绑定一致。",
            ],
        }
        return review

    def test_complete_record_is_valid_without_mutating_or_attesting_it(self):
        before = deepcopy(self.review)
        self.assertIs(validate_official_resource_review(self.review, self.binding), self.review)
        self.assertEqual(self.review, before)

    def test_reviewed_video_requires_separate_traceable_visual_and_original_audio_review(self):
        for mutation, code in (
            (lambda video: video.pop("videoModalityReview"),
             "official_video_modality_review_required"),
            (lambda video: video["videoModalityReview"]["visual"].update(intervals=[]),
             "official_video_modality_interval_invalid"),
            (lambda video: video["videoModalityReview"]["visual"].update(
                evidenceKind="subtitle_frames"), "official_video_visual_review_invalid"),
            (lambda video: video["videoModalityReview"]["audio"].update(
                originalTrackRendered=False), "official_video_audio_original_track_unreviewed"),
            (lambda video: video["videoModalityReview"]["audio"].update(
                evidenceKind="official_subtitle"), "official_video_audio_original_track_unreviewed"),
            (lambda video: video["videoModalityReview"]["audio"].update(
                method="仅对照公开字幕和ASR，未取得可听音轨。"),
             "official_video_audio_original_track_unreviewed"),
        ):
            with self.subTest(code=code):
                review = deepcopy(self.review)
                mutation(review["classHours"][0]["resources"]["video"])
                self.invalid(review, code)

    def test_subtitle_transcript_or_asr_is_only_supplementary_to_heard_original_audio(self):
        review = deepcopy(self.review)
        audio = review["classHours"][0]["resources"]["video"]["videoModalityReview"]["audio"]
        audio["supportingTextEvidence"] = [{
            "kind": "official_subtitle",
            "sourceUrl": review["classHours"][0]["courseUrl"],
            "sha256": "a" * 64,
            "role": "supplementary_only_not_audio_review",
        }]
        validate_official_resource_review(review, self.binding)
        for mutation in (
            lambda item: item.update(role="audio_review"),
            lambda item: item.update(kind="subtitle_as_audio"),
            lambda item: item.update(sourceUrl="https://example.com/subtitle.srt"),
            lambda item: item.update(sha256="not-a-sha"),
        ):
            changed = deepcopy(review)
            mutation(changed["classHours"][0]["resources"]["video"]
                     ["videoModalityReview"]["audio"]["supportingTextEvidence"][0])
            self.invalid(changed, "official_video_text_evidence_invalid")

    def test_real_official_no_audio_metadata_is_distinct_from_inaccessible_audio(self):
        review = deepcopy(self.review)
        audio = review["classHours"][0]["resources"]["video"]["videoModalityReview"]["audio"]
        audio.clear()
        audio.update({
            "status": "not_applicable", "sourceKind": "official_metadata_no_audio_track",
            "originalTrackRendered": False,
            "method": "逐项核对官方公开媒体元数据中的音频流计数。",
            "reviewedAt": review["reviewedAt"], "reviewedBy": review["reviewedBy"],
            "intervals": [], "findings": ["官方公开媒体元数据明确音频流数量为0。"],
            "supportingTextEvidence": [], "officialAudioStreamCount": 0,
            "metadataSourceUrl": review["classHours"][0]["courseUrl"],
            "metadataSha256": "b" * 64,
        })
        validate_official_resource_review(review, self.binding)
        for mutation in (
            lambda value: value.update(officialAudioStreamCount=1),
            lambda value: value.update(officialAudioStreamCount=False),
            lambda value: value.update(sourceKind="drm_audio_unavailable"),
            lambda value: value.update(findings=["音轨有DRM，GET返回401，当前无法取得。"]),
            lambda value: value.update(intervals=[{"start": "00:00", "end": "00:30"}]),
        ):
            changed = deepcopy(review)
            mutation(changed["classHours"][0]["resources"]["video"]
                     ["videoModalityReview"]["audio"])
            self.invalid(changed)

    def test_new_course_practice_maps_reviewed_after_class_location_to_an_original_course_page(self):
        draft = {
            'binding': deepcopy(self.binding),
            'pagePlan': [{'page': 1, 'type': 'interactive', 'title': '原创练习', 'move': '观察后修改。'}],
            'scopeReview': {'officialResourceReview': deepcopy(self.review)},
        }
        location = self.review['classHours'][0]['resources']['afterClassExercise']['locations'][0]
        draft['scopeReview']['postClassPractice'] = {
            'schemaVersion': POST_CLASS_PRACTICE_SCHEMA,
            'officialResourceReviewSha256': digest(self.review),
            'sourceKind': 'synthetic-reviewed-record', 'sourceSha256': 'a' * 64,
            'sourceContract': '合成测试来源合同。', 'originalFileDownloaded': False,
            'targetSeconds': 1800, 'goals': ['goal-one'],
            'inCoursePractice': [{
                'activityId': 'practice-one', 'goalId': 'goal-one', 'classHourId': 'lesson_1',
                'page': 1, 'sourceLocations': [location],
                'originalDesign': '保留目标，重新设计为可修改的原创互动。',
                'evidenceClaim': '只支持本次图片辅助操作的观察证据。',
            }],
        }
        self.assertIs(validate_new_course_post_class_practice(draft),
                      draft['scopeReview']['postClassPractice'])
        for mutation, code in (
            (lambda value: value['scopeReview'].pop('postClassPractice'),
             'post_class_practice_required'),
            (lambda value: value['scopeReview']['postClassPractice'].update(
                officialResourceReviewSha256='b' * 64), 'post_class_practice_review_mismatch'),
            (lambda value: value['scopeReview']['postClassPractice'].update(inCoursePractice=[]),
             'post_class_in_course_mapping_required'),
            (lambda value: value['scopeReview']['postClassPractice']['inCoursePractice'][0].update(
                sourceLocations=['不是已阅课后练习位置']), 'post_class_in_course_source_mismatch'),
        ):
            changed = deepcopy(draft)
            mutation(changed)
            with self.assertRaises(OfficialResourceReviewError) as caught:
                validate_new_course_post_class_practice(changed)
            self.assertEqual(str(caught.exception), code)

    def test_official_after_class_absence_is_reported_without_padding_a_goal(self):
        review = deepcopy(self.review)
        resource = review["classHours"][0]["resources"]["afterClassExercise"]
        resource.update(status="not_provided", locations=["官方本课时资源清单"],
                        findings=["官方本课时资源清单明确未提供课后练习。"])
        draft = {
            "binding": deepcopy(self.binding), "pagePlan": [],
            "scopeReview": {"officialResourceReview": review},
        }
        draft["scopeReview"]["postClassPractice"] = {
            "schemaVersion": POST_CLASS_PRACTICE_SCHEMA,
            "officialResourceReviewSha256": digest(review),
            "sourceKind": "official-inventory-absence", "sourceSha256": "a" * 64,
            "sourceContract": "只记录官方资源清单的缺项，不伪造官方练习目标。",
            "originalFileDownloaded": False, "targetSeconds": 0,
            "goals": [], "inCoursePractice": [],
            "officialGoalShortage": {
                "status": "official_after_class_exercise_not_provided",
                "classHourIds": ["lesson_1"],
                "sourceLocations": ["官方本课时资源清单"],
                "handling": ["课程可做原创巩固，但不声称继承了不存在的官方课后练习。"],
            },
        }
        validate_new_course_post_class_practice(draft)
        for mutation in (
            lambda practice: practice.update(targetSeconds=1),
            lambda practice: practice.update(goals=["padded-goal"]),
            lambda practice: practice.update(sourceKind="claimed-downloaded-file"),
            lambda practice: practice.update(originalFileDownloaded=True),
            lambda practice: practice.pop("officialGoalShortage"),
            lambda practice: practice["officialGoalShortage"].update(classHourIds=["lesson_2"]),
            lambda practice: practice["officialGoalShortage"].update(sourceLocations=["猜测位置"]),
        ):
            changed = deepcopy(draft)
            mutation(changed["scopeReview"]["postClassPractice"])
            with self.assertRaisesRegex(OfficialResourceReviewError,
                                        "post_class_official_goal_shortage_invalid"):
                validate_new_course_post_class_practice(changed)

    def test_partial_after_class_absence_is_scoped_and_cannot_receive_a_goal_mapping(self):
        review = deepcopy(self.review)
        second = deepcopy(review["classHours"][0])
        second["classHourId"] = "lesson_2"
        second["courseUrl"] = second["courseUrl"].replace("lesson_1", "lesson_2")
        for resource in second["resources"].values():
            resource["sourceUrl"] = second["courseUrl"]
        second_after = second["resources"]["afterClassExercise"]
        second_after.update(status="not_provided", locations=["官方第二课时资源清单"],
                            findings=["官方第二课时资源清单明确未提供课后练习。"])
        review["classHours"].append(second)
        first_location = review["classHours"][0]["resources"]["afterClassExercise"]["locations"][0]
        draft = {
            "binding": deepcopy(self.binding),
            "pagePlan": [{"page": 1, "type": "interactive", "title": "原创练习", "move": "观察后修改。"}],
            "scopeReview": {"officialResourceReview": review},
        }
        draft["scopeReview"]["postClassPractice"] = {
            "schemaVersion": POST_CLASS_PRACTICE_SCHEMA,
            "officialResourceReviewSha256": digest(review),
            "sourceKind": "mixed-reviewed-and-absence-record", "sourceSha256": "a" * 64,
            "sourceContract": "映射第一课时已阅目标，并单独报告第二课时官方缺项。",
            "originalFileDownloaded": True, "targetSeconds": 600, "goals": ["goal-one"],
            "inCoursePractice": [{
                "activityId": "practice-one", "goalId": "goal-one", "classHourId": "lesson_1",
                "page": 1, "sourceLocations": [first_location],
                "originalDesign": "以原创图片操作保留第一课时目标。",
                "evidenceClaim": "只支持当前操作观察，不覆盖缺项课时。",
            }],
            "officialGoalShortage": {
                "status": "official_after_class_exercise_not_provided",
                "classHourIds": ["lesson_2"], "sourceLocations": ["官方第二课时资源清单"],
                "handling": ["第二课时不创建或映射不存在的官方课后目标。"],
            },
        }
        validate_new_course_post_class_practice(draft)
        changed = deepcopy(draft)
        mapping = changed["scopeReview"]["postClassPractice"]["inCoursePractice"][0]
        mapping.update(classHourId="lesson_2", sourceLocations=["官方第二课时资源清单"])
        with self.assertRaisesRegex(OfficialResourceReviewError,
                                    "post_class_in_course_mapping_invalid"):
            validate_new_course_post_class_practice(changed)
        changed = deepcopy(draft)
        changed["scopeReview"]["postClassPractice"].pop("officialGoalShortage")
        with self.assertRaisesRegex(OfficialResourceReviewError,
                                    "post_class_official_goal_shortage_invalid"):
            validate_new_course_post_class_practice(changed)

    def test_explicit_unavailable_media_waivers_are_bound_and_leave_default_unchanged(self):
        review = self.media_waiver()
        before = deepcopy(review)
        validate_official_resource_review(review, self.binding)
        self.assertEqual(review, before)
        self.assertNotIn("reviewExceptions", self.review)
        self.assertTrue(all(resource["status"] == "reviewed"
                            for resource in self.review["classHours"][0]["resources"].values()))
        review.pop("reviewExceptions")
        self.invalid(review, "official_resource_unreviewed")

    def test_media_waiver_keeps_other_three_reviewed_or_strictly_absent_but_never_waived(self):
        for kind in ("teachingDesign", "learningTaskSheet", "afterClassExercise"):
            review = self.media_waiver()
            resource = review["classHours"][0]["resources"][kind]
            resource.update(
                status="not_provided",
                sourceUrl=review["classHours"][0]["courseUrl"],
                locations=[f"官方对应课时资源清单明确未列出{kind}。"],
                findings=[f"官方本课时确未提供{kind}资源，不从其他课借用。"],
            )
            validate_official_resource_review(review, self.binding)
            for status in ("unread", "waived_unavailable"):
                with self.subTest(kind=kind, status=status):
                    review = self.media_waiver()
                    review["classHours"][0]["resources"][kind]["status"] = status
                    self.invalid(review, "official_unwaivable_resource_unreviewed")
        review = self.media_waiver()
        review["reviewExceptions"][0]["resourceType"] = "teachingDesign"
        self.invalid(review, "official_resource_exception_type_invalid")

    def test_media_waiver_needs_exact_binding_hour_user_instruction_time_and_reason(self):
        for field in BINDING_FIELDS:
            review = self.media_waiver()
            review["reviewExceptions"][0]["binding"][field] = "other-lesson"
            self.invalid(review, "official_resource_exception_binding_mismatch")
        for field, value, code in (
            ("classHourIds", ["lesson_2"], "official_resource_exception_hours_invalid"),
            ("classHourIds", ["lesson_1", "lesson_1"], "official_resource_exception_hours_invalid"),
            ("authorizedBy", "assistant", "official_resource_exception_authorization_missing"),
            ("userInstruction", "", "official_resource_exception_authorization_missing"),
            ("reason", "", "official_resource_exception_authorization_missing"),
            ("authorizedAt", "2026-10-26T17:00:00", "official_resource_exception_date_invalid"),
        ):
            with self.subTest(field=field):
                review = self.media_waiver()
                review["reviewExceptions"][0][field] = value
                self.invalid(review, code)

    def test_media_waiver_cannot_spill_into_another_lesson_or_unrecorded_hour(self):
        review = self.media_waiver()
        changed_binding = {**self.binding, "nodeId": "a-new-lesson"}
        review["binding"] = changed_binding
        with self.assertRaisesRegex(OfficialResourceReviewError, "exception_binding_mismatch"):
            validate_official_resource_review(review, changed_binding)
        review = self.media_waiver()
        second = deepcopy(review["classHours"][0])
        second["classHourId"] = "lesson_2"
        second["courseUrl"] = second["courseUrl"].replace("lesson_1", "lesson_2")
        for resource in second["resources"].values():
            resource["sourceUrl"] = second["courseUrl"]
        review["classHours"].append(second)
        self.invalid(review, "official_resource_unreviewed")

    def test_waiver_record_does_not_turn_into_reviewed_or_an_unscoped_permission(self):
        review = self.media_waiver()
        video = review["classHours"][0]["resources"]["video"]
        video["status"] = "reviewed"
        video["videoModalityReview"] = deepcopy(
            self.review["classHours"][0]["resources"]["video"]["videoModalityReview"])
        self.invalid(review, "official_resource_exception_scope_unused")
        review = self.media_waiver()
        review["reviewExceptions"].append(deepcopy(review["reviewExceptions"][0]))
        self.invalid(review, "official_resource_exception_duplicate")
        review = self.media_waiver()
        review["classHours"][0]["resources"]["video"]["sourceUrl"] = (
            "https://s-file-1.ykt.cbern.com.cn/unavailable-video.mp4")
        self.invalid(review, "official_resource_exception_source_invalid")

    def test_missing_record_and_each_resource_are_rejected(self):
        self.invalid(None, "official_resource_review_required")
        for kind in REQUIRED_RESOURCES:
            with self.subTest(kind=kind):
                review = deepcopy(self.review)
                del review["classHours"][0]["resources"][kind]
                self.invalid(review, "official_resources_incomplete")

    def test_each_binding_identity_must_match(self):
        for field in BINDING_FIELDS:
            with self.subTest(field=field):
                review = deepcopy(self.review)
                review["binding"][field] = "different"
                self.invalid(review, "official_textbook_binding_mismatch")
        for field in ("gradeCode", "subject", "volume"):
            review = deepcopy(self.review)
            review["officialTextbook"][field] = "different"
            self.invalid(review, "official_textbook_identity_mismatch")

    def test_unread_and_blocked_states_cannot_pass(self):
        for state in ("unread", "blocked", "pending", "missing", "login_required", ""):
            with self.subTest(state=state):
                review = deepcopy(self.review)
                review["classHours"][0]["resources"]["video"]["status"] = state
                self.invalid(review, "official_resource_unreviewed")

    def test_reviewed_status_cannot_override_explicit_unread_or_access_disclosures(self):
        for note in ("尚未观看，登录受阻，待获取视频", "只看到标题，还没有阅读课件",
                     "本次尚未完整观看视频。", "课件尚未阅读。", "目前无法访问视频。",
                     "需要登录。", "待获取视频。", "实际审阅：未完成阅读课件。",
                     "仅显示封面。", "not yet watched", "login required"):
            with self.subTest(note=note):
                review = deepcopy(self.review)
                review["classHours"][0]["resources"]["video"]["findings"] = [note]
                self.invalid(review, "official_resource_unreviewed")

    def test_pedagogical_findings_are_not_mistaken_for_unread_resources(self):
        for note in ("学生尚未掌握目标，教师用生活情境帮助理解。",
                     "课件没有阅读门槛，非目标指令用图片和语音表达。",
                     "先自主阅读再教师示范，并请学生修改自己的作品。",
                     "教师先了解未阅读课文的学生的困难，再安排伙伴共读。",
                     "已经登录并完整观看视频，前半段先识词，后半段描写和修改。",
                     "此前登录失败，现已完整观看视频并核对时间词排序环节。"):
            with self.subTest(note=note):
                review = deepcopy(self.review)
                review["classHours"][0]["resources"]["video"]["findings"] = [note]
                validate_official_resource_review(review, self.binding)

    def test_review_needs_concrete_locations_findings_and_original_adaptation(self):
        for field in ("locations", "findings"):
            review = deepcopy(self.review)
            review["classHours"][0]["resources"]["video"][field] = []
            self.invalid(review, "official_resource_findings_missing")
        for field in self.review["adaptation"]:
            review = deepcopy(self.review)
            review["adaptation"][field] = [" "]
            self.invalid(review, "official_resource_adaptation_missing")
        review = deepcopy(self.review)
        review["officialTextbook"]["editionMatchEvidence"] = ""
        self.invalid(review, "official_textbook_identity_incomplete")

    def test_not_provided_requires_official_inventory_absence_not_access_failure(self):
        review = deepcopy(self.review)
        resource = review["classHours"][0]["resources"]["learningTaskSheet"]
        resource.update(status="not_provided", locations=["官方本课时资源清单"],
                        findings=["官方本课时资源清单明确未提供学习任务单。"])
        validate_official_resource_review(review, self.binding)
        for note in ("", "没有看过", "官方资源未提供，因为登录失败。", "官方资源未提供，页面404。"):
            with self.subTest(note=note):
                broken = deepcopy(review)
                broken["classHours"][0]["resources"]["learningTaskSheet"]["findings"] = [note]
                self.invalid(broken)
        resource["sourceUrl"] = "https://s-file-1.ykt.cbern.com.cn/absent.pdf"
        self.invalid(review, "official_resource_absence_unverified")

    def test_class_hour_and_official_material_ids_cannot_be_guessed_or_mixed(self):
        original = self.review["classHours"][0]["courseUrl"]
        for url in (original.replace("lesson_1", "lesson_2"),
                    original.replace("material-one", "other-resource-id"),
                    original.replace("&chapterId=chapter-one", ""),
                    original + "&classHourId=lesson_1"):
            review = deepcopy(self.review)
            review["classHours"][0]["courseUrl"] = url
            self.invalid(review)
        review = deepcopy(self.review)
        review["classHours"].append(deepcopy(review["classHours"][0]))
        self.invalid(review, "official_class_hour_invalid")
        review = deepcopy(self.review)
        review["classHours"][0]["resources"]["video"]["sourceUrl"] = original.replace("lesson_1", "lesson_2")
        self.invalid(review, "official_resource_class_hour_mismatch")

    def test_exact_legacy_prepare_detail_identity_is_accepted_without_weakening_standard_route(self):
        review = self.legacy_prepare_review()
        validate_official_resource_review(review, self.binding)
        standard = deepcopy(self.review)
        standard["classHours"][0]["legacyCourseIdentity"] = deepcopy(
            review["classHours"][0]["legacyCourseIdentity"])
        self.invalid(standard, "official_legacy_course_identity_unexpected")

    def test_legacy_prepare_detail_needs_explicit_current_catalog_binding(self):
        for mutation in (
            lambda hour: hour.pop("legacyCourseIdentity"),
            lambda hour: hour["legacyCourseIdentity"].update(lessonId="other-lesson"),
            lambda hour: hour["legacyCourseIdentity"].update(teachingMaterialId="other-material"),
            lambda hour: hour["legacyCourseIdentity"].update(editionId="other-edition"),
            lambda hour: hour["legacyCourseIdentity"].update(revisionId="other-revision"),
            lambda hour: hour["legacyCourseIdentity"].update(nodeId="other-node"),
            lambda hour: hour["legacyCourseIdentity"].update(evidenceLocations=[]),
            lambda hour: hour["legacyCourseIdentity"].update(unreviewedExtra="not-allowed"),
        ):
            review = self.legacy_prepare_review()
            mutation(review["classHours"][0])
            self.invalid(review, "official_legacy_course_identity_mismatch")

    def test_legacy_prepare_detail_rejects_mixed_hours_routes_and_extra_query_identity(self):
        review = self.legacy_prepare_review()
        hour = review["classHours"][0]
        hour["courseUrl"] += "&activityId=guessed"
        self.invalid(review, "official_legacy_course_identity_missing")
        review = self.legacy_prepare_review()
        review["classHours"][0]["resources"]["video"]["sourceUrl"] = (
            "https://basic.smartedu.cn/syncClassroom/prepare/detail?"
            "lessonId=other-lesson&classHourId=lesson_1")
        self.invalid(review, "official_resource_class_hour_mismatch")
        review = self.legacy_prepare_review()
        review["classHours"][0]["resources"]["video"]["sourceUrl"] = (
            self.review["classHours"][0]["courseUrl"])
        self.invalid(review, "official_resource_class_hour_mismatch")

    def test_only_public_official_urls_without_credentials_are_accepted(self):
        for url in ("http://basic.smartedu.cn/resource", "https://example.com/file.pdf",
                    "https://basic.smartedu.cn.evil.test/file.pdf",
                    "https://user:private@basic.smartedu.cn/resource",
                    "https://s-file-1.ykt.cbern.com.cn/file.pdf?X-Amz-Signature=private",
                    "https://s-file-1.ykt.cbern.com.cn/file.pdf?token=private",
                    "https://s-file-1.ykt.cbern.com.cn/file.pdf?sign=private"):
            with self.subTest(url=url):
                review = deepcopy(self.review)
                review["classHours"][0]["resources"]["video"]["sourceUrl"] = url
                self.invalid(review, "official_resource_url_invalid")
        self.review["classHours"][0]["resources"]["courseware"]["sourceUrl"] = (
            "https://s-file-1.ykt.cbern.com.cn/public-course.pdf")
        validate_official_resource_review(self.review, self.binding)

    def test_dates_reviewer_and_every_class_hour_must_be_complete(self):
        for field, value in (("reviewedAt", "not-a-date"), ("reviewedAt", "2026-10-26T08:00:00"),
                             ("reviewedBy", "")):
            review = deepcopy(self.review)
            review[field] = value
            self.invalid(review)
        review = deepcopy(self.review)
        review["officialTextbook"]["publicationDate"] = "2024-13"
        self.invalid(review)
        review = deepcopy(self.review)
        review["classHours"][0]["learningObjectives"] = []
        self.invalid(review, "official_class_hour_invalid")
        review = deepcopy(self.review)
        second = deepcopy(review["classHours"][0])
        second["classHourId"] = "lesson_2"
        second["courseUrl"] = second["courseUrl"].replace("lesson_1", "lesson_2")
        del second["resources"]["afterClassExercise"]
        review["classHours"].append(second)
        self.invalid(review, "official_resources_incomplete")
