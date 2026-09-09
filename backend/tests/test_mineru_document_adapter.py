from __future__ import annotations

import json
import unittest

from integrations.mineru_document_adapter import (
    MinerUDocumentAdapter,
    MinerUDocumentError,
)


class MinerUDocumentAdapterTest(unittest.TestCase):
    def test_parses_official_self_hosted_contract_and_bounds_generation_context(self):
        calls: list[tuple[str, bytes, dict[str, str], float]] = []
        response = {
            "results": {
                "语文讲义.pdf": {
                    "md_content": "a" * 50_010,
                    "images": {"images/mouth-a.png": "YWJj"},
                    "content_list": [
                        {
                            "type": "image",
                            "img_path": "images/mouth-a.png",
                            "page_idx": 1,
                            "bbox": [10, 20, 210, 120],
                            "image_caption": ["单韵母 a 的口型示意"],
                        },
                        {"type": "text", "page_idx": 0, "text": "单韵母"},
                    ],
                }
            }
        }

        def transport(url, body, headers, timeout):
            calls.append((url, body, dict(headers), timeout))
            return 200, json.dumps(response, ensure_ascii=False).encode("utf-8")

        adapter = MinerUDocumentAdapter(
            base_url="http://mineru.internal:8000/",
            transport=transport,
        )
        document = adapter.parse(
            file_name="教材/语文讲义.pdf",
            content=b"%PDF-test",
            mime_type="application/pdf",
        )

        self.assertEqual(document.file_name, "语文讲义.pdf")
        self.assertEqual(document.page_count, 2)
        self.assertEqual(document.images[0].page_number, 2)
        self.assertEqual(document.images[0].bbox, (10.0, 20.0, 210.0, 120.0))
        self.assertEqual(document.images[0].caption, "单韵母 a 的口型示意")
        context = adapter.grounding_payload(document)
        self.assertEqual(len(context["markdown"]), 50_000)
        self.assertTrue(context["truncated"])
        self.assertEqual(len(context["images"]), 1)

        self.assertEqual(calls[0][0], "http://mineru.internal:8000/file_parse")
        multipart = calls[0][1]
        self.assertIn(b'name="parse_method"', multipart)
        self.assertIn(b"auto", multipart)
        self.assertIn(b'name="return_content_list"', multipart)
        self.assertIn(b'name="return_images"', multipart)
        self.assertNotIn(b"Authorization", multipart)

    def test_rejects_unconfigured_unsupported_empty_and_oversized_documents(self):
        adapter = MinerUDocumentAdapter(base_url="", max_file_bytes=4)
        cases = (
            ("empty.pdf", b"", "application/pdf", "mineru_empty_file"),
            ("notes.txt", b"x", "text/plain", "mineru_unsupported_file"),
            ("large.pdf", b"12345", "application/pdf", "mineru_file_too_large"),
            ("ok.pdf", b"pdf", "application/pdf", "mineru_not_configured"),
        )
        for name, content, mime, expected_code in cases:
            with self.subTest(name=name), self.assertRaises(MinerUDocumentError) as raised:
                adapter.parse(file_name=name, content=content, mime_type=mime)
            self.assertEqual(raised.exception.code, expected_code)

    def test_fails_closed_for_http_and_malformed_responses(self):
        failures = (
            (lambda *_args: (503, b"down"), "mineru_request_failed"),
            (lambda *_args: (200, b"not-json"), "mineru_invalid_response"),
            (lambda *_args: (200, b'{"results":{}}'), "mineru_no_result"),
        )
        for transport, expected_code in failures:
            with self.subTest(expected_code=expected_code):
                adapter = MinerUDocumentAdapter(
                    base_url="https://mineru.example",
                    transport=transport,
                )
                with self.assertRaises(MinerUDocumentError) as raised:
                    adapter.parse(
                        file_name="course.pdf",
                        content=b"pdf",
                        mime_type="application/pdf",
                    )
                self.assertEqual(raised.exception.code, expected_code)


if __name__ == "__main__":
    unittest.main()
