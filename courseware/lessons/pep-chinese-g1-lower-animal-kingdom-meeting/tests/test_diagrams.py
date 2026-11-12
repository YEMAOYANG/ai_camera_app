from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location("meeting_diagrams", ROOT / "diagrams.py")
diagrams = module_from_spec(spec)
spec.loader.exec_module(diagrams)


class MeetingDiagramTests(unittest.TestCase):
    def test_correct_seven_stroke_counts_and_final_components(self):
        paths = diagrams.STROKES
        self.assertEqual([len(paths[c]) for c in "国都百听时点林"], [8, 10, 6, 7, 7, 9, 8])
        self.assertGreater(paths["国"][-1][-1][0], paths["国"][-1][0][0])
        self.assertEqual(paths["都"][-1][0][0], paths["都"][-1][-1][0])
        starts = [line[0][0] for line in paths["点"][-4:]]
        self.assertEqual(starts, sorted(starts))
        self.assertGreater(paths["林"][-1][-1][0], paths["林"][-1][0][0])

    def test_four_rounds_each_keep_ten_repeat_marks_and_clock_at_eight(self):
        items={name:Image.new("RGBA",(40,40),"#66a385") for name in ("dock-date","dock-place")}
        sheet=diagrams.notice_tally(items,diagrams.STORY_MASKS).convert("RGB")
        marks=(36,69,60)
        for x,y in ((171,91),(508,91),(171,296),(508,296)):
            self.assertEqual(sum(sheet.getpixel((x-108+24*i,y+83))==marks for i in range(10)),10)
        face=diagrams.clock(8).convert("RGB")
        self.assertEqual(face.getpixel((120,70)),marks)
        self.assertEqual(face.getpixel((90,138)),marks)
