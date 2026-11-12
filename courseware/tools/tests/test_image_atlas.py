from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

from courseware.tools.image_atlas import contact_sheet, render_prompt, split_atlas


COLORS = ['#ff0000', '#00ff00', '#0000ff', '#f48b00', '#ffffff', '#000000']


def make_plan(background='transparent'):
    return {'atlasId': 'classroom-objects', 'rows': 2, 'columns': 3, 'background': background,
            'assets': [{'assetKey': f'picture-{i}', 'description': f'One {color} object', 'usedBy': [f's03/q{i}']}
                       for i, color in enumerate(COLORS)]}


class ImageAtlasTests(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.lesson = Path(workspace.name) / 'lesson'
        self.source_dir = self.lesson / 'art-source'
        self.source_dir.mkdir(parents=True)
        self.source = self.source_dir / 'original.png'
        self.plan = make_plan()
        self.sent = '正式拼板提示\nExact submitted prompt.\n'.encode()

    def make_sheet(self, *, transparent=True, clipped=False):
        image = Image.new('RGBA' if transparent else 'RGB', (803, 537),
                          (0, 0, 0, 0) if transparent else '#fff2df')
        draw = ImageDraw.Draw(image)
        for i, color in enumerate(COLORS):
            row, col = divmod(i, 3)
            left, top = col * 803 // 3, row * 537 // 2
            offset = 0 if clipped and i == 0 else 35
            draw.rectangle((left + offset, top + 35, left + 145, top + 145), fill=color)
        image.save(self.source)

    def test_prompt_records_row_order_and_visual_constraints(self):
        prompt = render_prompt(self.plan)
        self.assertIn('Use 2 equal rows and 3 equal columns', prompt)
        self.assertIn('true transparent alpha', prompt)
        self.assertIn('Row 1, column 3: One #0000ff object', prompt)
        self.assertIn('Row 2, column 1: One #f48b00 object', prompt)
        self.assertIn('counting appears exactly once', prompt)
        self.assertIn('uniform warm cream', render_prompt(make_plan('cream')))

    def test_odd_dimensions_crop_and_register_exact_prompt_and_bytes(self):
        self.make_sheet()
        receipt_path = split_atlas(self.plan, self.lesson, self.source, self.sent)
        receipt = json.loads(receipt_path.read_text())
        self.assertEqual(receipt['sheetPixels'], [803, 537])
        self.assertEqual([asset['sourceCrop'] for asset in receipt['assets']], [
            [0, 0, 267, 268], [267, 0, 535, 268], [535, 0, 803, 268],
            [0, 268, 267, 537], [267, 268, 535, 537], [535, 268, 803, 537],
        ])
        for i, asset in enumerate(receipt['assets']):
            self.assertEqual(asset['generatedSource'], 'art-source/original.png')
            self.assertEqual(asset['generatedSourceSha256'], sha256(self.source.read_bytes()).hexdigest())
            self.assertEqual(asset['prompt'], self.sent.decode())
            self.assertEqual(asset['promptSha256'], sha256(self.sent).hexdigest())
            self.assertEqual(asset['visualReview'], 'pending')
            self.assertEqual(asset['usedBy'], [f's03/q{i}'])
            path = self.lesson / asset['path']
            self.assertEqual(asset['sha256'], sha256(path.read_bytes()).hexdigest())
            with Image.open(path) as image:
                self.assertEqual(image.size, (asset['width'], asset['height']))
                self.assertEqual(image.getpixel((0, 0))[3], 0)
                self.assertEqual(image.getpixel((60, 60)), (*bytes.fromhex(COLORS[i][1:]), 255))

    def test_equal_rerun_is_idempotent_and_missing_asset_is_recreated(self):
        self.make_sheet()
        receipt = split_atlas(self.plan, self.lesson, self.source, self.sent)
        original = receipt.read_bytes()
        file = self.lesson / 'assets/picture-2.png'
        data = file.read_bytes()
        file.unlink()
        self.assertEqual(split_atlas(self.plan, self.lesson, self.source, self.sent), receipt)
        self.assertEqual(file.read_bytes(), data)
        self.assertEqual(receipt.read_bytes(), original)
        with self.assertRaisesRegex(ValueError, 'refusing to replace existing output'):
            split_atlas(self.plan, self.lesson, self.source, b'different prompt')

    def test_refuses_existing_different_asset_before_writing_other_assets(self):
        self.make_sheet()
        assets = self.lesson / 'assets'
        assets.mkdir()
        existing = assets / 'picture-5.png'
        existing.write_bytes(b'existing output')
        with self.assertRaisesRegex(ValueError, 'refusing to replace existing output'):
            split_atlas(self.plan, self.lesson, self.source, self.sent)
        self.assertEqual(list(assets.iterdir()), [existing])
        self.assertEqual(existing.read_bytes(), b'existing output')
        self.assertEqual(list(self.source_dir.glob('*.receipt.json')), [])

    def test_simultaneous_batches_cannot_mix_output(self):
        self.make_sheet()
        alternative = self.source_dir / 'other.png'
        with Image.open(self.source) as original:
            original.transpose(Image.Transpose.FLIP_TOP_BOTTOM).save(alternative)
        other_plan = {**self.plan, 'atlasId': 'other-objects'}
        with ThreadPoolExecutor(max_workers=2) as workers:
            tasks = [workers.submit(split_atlas, plan, self.lesson, sheet, self.sent)
                     for plan, sheet in [(self.plan, self.source), (other_plan, alternative)]]
        receipts = []
        for task in tasks:
            try:
                receipts.append(task.result())
            except ValueError as error:
                self.assertIn('refusing to replace existing output', str(error))
        self.assertEqual(len(receipts), 1)
        receipt = json.loads(receipts[0].read_text())
        for asset in receipt['assets']:
            self.assertEqual(sha256((self.lesson / asset['path']).read_bytes()).hexdigest(), asset['sha256'])

    def test_rejects_wrong_alpha_empty_or_clipped_slots_and_overlapping_crops(self):
        self.make_sheet(transparent=False)
        with self.assertRaisesRegex(ValueError, 'opaque or touches its border'):
            split_atlas(self.plan, self.lesson, self.source, self.sent)
        self.make_sheet(clipped=True)
        with self.assertRaisesRegex(ValueError, 'opaque or touches its border'):
            split_atlas(self.plan, self.lesson, self.source, self.sent)
        Image.new('RGBA', (803, 537)).save(self.source)
        with self.assertRaisesRegex(ValueError, 'crop is empty'):
            split_atlas(self.plan, self.lesson, self.source, self.sent)
        self.make_sheet()
        self.plan['assets'][0]['crop'] = [0, 0, 280, 267]
        with self.assertRaisesRegex(ValueError, 'overlaps a previous crop'):
            split_atlas(self.plan, self.lesson, self.source, self.sent)
        self.assertFalse((self.lesson / 'assets').exists())

    def test_manual_crop_and_small_opaque_outputs(self):
        self.make_sheet(transparent=False)
        plan = make_plan('cream')
        plan['assets'][0]['crop'] = [10, 10, 190, 210]
        receipt = split_atlas(plan, self.lesson, self.source, self.sent, inset=4, max_edge=128)
        first = json.loads(receipt.read_text())['assets'][0]
        self.assertEqual(first['sourceCrop'], [10, 10, 190, 210])
        with Image.open(self.lesson / first['path']) as image:
            self.assertEqual(image.mode, 'RGB')
            self.assertEqual(image.size, (115, 128))

    def test_rejects_invalid_plan_and_source_outside_lesson(self):
        for edit in ({'atlasId': '../wrong'}, {'background': []}, {'rows': '2'}, {'assets': []}):
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                render_prompt({**self.plan, **edit})
        bad = deepcopy(self.plan)
        bad['assets'][0]['assetKey'] = bad['assets'][1]['assetKey']
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            render_prompt(bad)
        self.make_sheet()
        with self.assertRaisesRegex(ValueError, 'keep the original sheet'):
            split_atlas(self.plan, self.source_dir, self.source, self.sent)

    def test_review_is_limited_to_twelve_images_and_1600_pixels(self):
        self.make_sheet()
        self.assertEqual(contact_sheet([self.source] * 12).size, (1600, 1200))
        with self.assertRaisesRegex(ValueError, '1–12'):
            contact_sheet([self.source] * 13)


if __name__ == '__main__':
    unittest.main()
