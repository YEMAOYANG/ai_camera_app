from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import shutil
import tempfile
import unittest

from courseware.tools import lane
from courseware.tools.tests.test_lane import FakeService, FIXTURE


class LaneDispatchedMediaTest(unittest.TestCase):
    def test_cache_only_mode_requires_media_dispatch_and_reuses_completed_media(self):
        with tempfile.TemporaryDirectory() as directory:
            lesson = Path(directory) / 'lesson'
            work = Path(directory) / 'work'
            shutil.copytree(FIXTURE, lesson)
            args = ['--lesson', str(lesson), '--work', str(work), '--stage-id', 'test-lane',
                    '--steps', 'build', '--cached-media-only']
            with redirect_stderr(io.StringIO()) as diagnostics:
                self.assertEqual(lane.main(args), 1)
            self.assertIn('courseware.tools.media_dispatch', diagnostics.getvalue())
            self.assertFalse((work / 'body.json').exists())
            lane.run_lesson(lesson, work, stage_id='test-lane', steps=['build'], post=FakeService().post)
            with redirect_stdout(io.StringIO()) as summary:
                self.assertEqual(lane.main(args), 0)
            self.assertIn('"voiced": 0', summary.getvalue())
