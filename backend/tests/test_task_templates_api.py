from __future__ import annotations

import json
import unittest

from app import create_app
from tests.support import fresh_test_config, request_debug_code


FORBIDDEN_TEMPLATE_WORDS = ("数学", "英语", "作业", "练题", "背单词", "书包检查")
FORBIDDEN_TITLE_PREFIXES = ("小班", "中班", "大班")


class TaskTemplatesApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(fresh_test_config())
        self.client = self.app.test_client()
        self.access_token = self._login("13800003126")
        self.child_id = self._create_child("小禾", grade="中班")

    def test_lists_kindergarten_templates_and_labels(self):
        response = self.client.get("/api/tasks/templates", headers=self._auth_headers())

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["ok"])
        templates = response.json["templates"]
        self.assertGreaterEqual(len(templates), 30)
        counts = {"small": 0, "middle": 0, "big": 0}
        for template in templates:
            counts[template["grade"]] += 1
            self.assertIn("gradeLabel", template)
            self.assertIn("dayTypeLabel", template)
            self.assertIn("tagLabels", template)
            self.assertTrue(template["rows"])
        self.assertGreaterEqual(counts["small"], 10)
        self.assertGreaterEqual(counts["middle"], 10)
        self.assertGreaterEqual(counts["big"], 13)

    def test_filters_by_grade_day_type_and_tag(self):
        grade_response = self.client.get(
            "/api/tasks/templates",
            query_string={"grade": "small"},
            headers=self._auth_headers(),
        )
        self.assertEqual(grade_response.status_code, 200)
        self.assertGreaterEqual(len(grade_response.json["templates"]), 10)
        self.assertEqual({item["grade"] for item in grade_response.json["templates"]}, {"small"})

        weekend_response = self.client.get(
            "/api/tasks/templates",
            query_string={"grade": "middle", "dayType": "weekend"},
            headers=self._auth_headers(),
        )
        self.assertEqual(weekend_response.status_code, 200)
        self.assertTrue(weekend_response.json["templates"])
        self.assertEqual(
            {item["dayType"] for item in weekend_response.json["templates"]},
            {"weekend"},
        )

        reading_response = self.client.get(
            "/api/tasks/templates",
            query_string={"grade": "big", "tag": "reading"},
            headers=self._auth_headers(),
        )
        self.assertEqual(reading_response.status_code, 200)
        self.assertTrue(reading_response.json["templates"])
        for template in reading_response.json["templates"]:
            self.assertIn("reading", template["tags"])

        school_ready_response = self.client.get(
            "/api/tasks/templates",
            query_string={"grade": "big", "tag": "school_ready"},
            headers=self._auth_headers(),
        )
        self.assertEqual(school_ready_response.status_code, 200)
        self.assertGreaterEqual(len(school_ready_response.json["templates"]), 3)
        for template in school_ready_response.json["templates"]:
            self.assertIn("school_ready", template["tags"])
            self.assertEqual(template["grade"], "big")

    def test_child_id_recommends_grade_and_is_family_scoped(self):
        response = self.client.get(
            "/api/tasks/templates",
            query_string={"childId": self.child_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["recommendedGrade"], "middle")
        self.assertEqual({item["grade"] for item in response.json["templates"]}, {"middle"})

        other_access = self._login("13800003127")
        other_child = self._create_child_with_token(other_access, "小远", grade="小班")
        forbidden = self.client.get(
            "/api/tasks/templates",
            query_string={"childId": other_child},
            headers=self._auth_headers(),
        )
        self.assertEqual(forbidden.status_code, 404)
        self.assertEqual(forbidden.json["error"], "child_not_found")

    def test_templates_do_not_include_school_task_words(self):
        response = self.client.get("/api/tasks/templates", headers=self._auth_headers())
        self.assertEqual(response.status_code, 200)
        text = json.dumps(response.json, ensure_ascii=False)
        for word in FORBIDDEN_TEMPLATE_WORDS:
            self.assertNotIn(word, text)

    def test_template_titles_do_not_repeat_grade_prefix(self):
        response = self.client.get("/api/tasks/templates", headers=self._auth_headers())
        self.assertEqual(response.status_code, 200)
        for template in response.json["templates"]:
            title = template["title"]
            self.assertFalse(
                title.startswith(FORBIDDEN_TITLE_PREFIXES),
                f"template title should not repeat grade prefix: {title}",
            )

    def _login(self, phone: str) -> str:
        code = request_debug_code(self.client, phone)
        login = self.client.post("/api/auth/sms/login", json={"phone": phone, "code": code})
        self.assertEqual(login.status_code, 200)
        return login.json["tokens"]["accessToken"]

    def _create_child(self, name: str, *, grade: str) -> str:
        return self._create_child_with_token(self.access_token, name, grade=grade)

    def _create_child_with_token(self, access_token: str, name: str, *, grade: str) -> str:
        headers = {"Authorization": f"Bearer {access_token}"}
        parent = self.client.post(
            "/api/setup/parent-identity",
            json={"displayName": "妈妈", "relationship": "妈妈", "relationshipKey": "mom"},
            headers=headers,
        )
        self.assertEqual(parent.status_code, 200)
        child = self.client.post(
            "/api/setup/child",
            json={
                "name": name,
                "nickname": name,
                "educationStage": "幼儿园",
                "ageStage": f"幼儿园{grade}",
                "grade": grade,
                "birthday": "2021-09-01",
            },
            headers=headers,
        )
        self.assertEqual(child.status_code, 200)
        return child.json["child"]["id"]

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}


if __name__ == "__main__":
    unittest.main()
