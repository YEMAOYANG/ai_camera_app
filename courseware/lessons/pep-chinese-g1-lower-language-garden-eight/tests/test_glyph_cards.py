import importlib.util
import json
from pathlib import Path
import unittest


ART = Path(__file__).resolve().parents[1] / 'art-source'
SPEC = importlib.util.spec_from_file_location('garden8_glyphs', ART / 'draw_garden8_glyphs.py')
GLYPHS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GLYPHS)
CARDS = json.loads((ART / 'garden8-glyph-cards.json').read_text(encoding='utf-8'))['cards']


class GlyphCardTests(unittest.TestCase):
    def test_addition_and_subtraction_preserve_the_printed_parts(self):
        cells = CARDS['join-parts']['cells']
        self.assertEqual(''.join(cell['glyph'] for cell in cells), '口+少=吵王+见=现丁+页=顶月+半=胖')
        cells = CARDS['take-parts']['cells']
        self.assertEqual(''.join(cell['glyph'] for cell in cells), '飘−风=票房−方=户校−木=交爸−巴=父')
        self.assertEqual([cell['glyph'] for cell in cells if cell.get('muted')], list('风方木巴'))

    def test_sentence_has_two_empty_cells_and_its_own_punctuation_cells(self):
        cells = CARDS['sentence-grid']['cells']
        self.assertEqual([cell['glyph'] for cell in cells[:2]], ['', ''])
        self.assertEqual(''.join(cell['glyph'] for cell in cells), '雨停了，我很高兴。')
        self.assertEqual([cell['glyph'] for cell in cells if cell.get('punctuation')], ['，', '。'])
        self.assertTrue(all(cell['grid'] for cell in cells))

    def test_every_glyph_cell_is_inside_its_frame(self):
        for name, card in CARDS.items():
            width, height = card['canvas']
            for cell in card['cells']:
                x, y, w, h = cell['bounds']
                with self.subTest(card=name, glyph=cell['glyph']):
                    self.assertTrue(0 <= x < x + w < width)
                    self.assertTrue(0 <= y < y + h < height)


if __name__ == '__main__':
    unittest.main()
