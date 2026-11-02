import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from scripts.textbook_page_harness import PAGE, build


class TextbookPageHarnessSourceTests(TestCase):
    def test_stub_matches_the_runtime_narration_bridge_shape(self):
        self.assertIn("narrationState(id,'playing')", PAGE)
        self.assertIn("narrationState(id,'ready')", PAGE)
        self.assertIn('return Promise.resolve(true)', PAGE)
        self.assertIn('window.miraCancelNarration=function()', PAGE)

    def test_registered_source_uses_current_course_file_bytes(self):
        classroom = {
            'scenes': [
                {
                    'type': 'slide',
                    'title': 'current remote scene',
                    'content': {'type': 'slide'},
                },
            ],
        }
        with TemporaryDirectory() as folder:
            source = Path(folder) / 'registered-snapshot.json'
            target = Path(folder) / 'harness'
            with patch(
                'scripts.textbook_page_harness.course_text',
                return_value=json.dumps(classroom),
            ) as current_bytes:
                self.assertEqual(build(source, target), 1)

            current_bytes.assert_called_once_with(source)
            pages = json.loads((target / 'pages.json').read_text(encoding='utf-8'))
            self.assertEqual(pages[0]['title'], 'current remote scene')

