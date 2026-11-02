import hashlib
import io
import unittest

from PIL import Image

from courseware.tools.glyph_picture import _is_emoji, _layout_cells, png_name, render_picture


class GlyphPictureTests(unittest.TestCase):
    def test_png_deterministic_and_named_by_hash(self):
        spec = {'groups': [{'cells': [{'glyph': '🦆'} for _ in range(5)]}], 'separator': 'gap'}
        png = render_picture(spec)
        image = Image.open(io.BytesIO(png))
        self.assertEqual(image.format, 'PNG')
        self.assertEqual(image.size, (480, 240))
        self.assertEqual(png, render_picture(spec))
        self.assertEqual(png_name(png), hashlib.sha256(png).hexdigest() + '.png')

    def test_layout_counts_and_wrapping(self):
        for count in (0, 1, 8, 9, 17):
            cells = [{'glyph': str(i)} for i in range(count)]
            spec = {'groups': [{'cells': cells}, {'cells': [{'glyph': '？'}]}], 'separator': 'plus'}
            layout, signs, width, height = _layout_cells(spec)
            self.assertEqual([cell for _, _, cell in layout], cells + [{'glyph': '？'}])
            self.assertEqual(len({(x, y) for x, y, _ in layout}), count + 1)
            self.assertEqual(height, 2 if count > 8 else 1)
            self.assertEqual(len(signs), 1)
            self.assertTrue(all(0 <= x < width and 0 <= y < height for x, y, _ in layout))
        render_picture(spec)

    def test_symbol_emoji_use_the_emoji_font(self):
        for glyph in ('🦆', '⚽', '⚪', '🔴'):
            self.assertTrue(_is_emoji(glyph), glyph)
        for glyph in ('3', '＝', '−', '？', '＋'):
            self.assertFalse(_is_emoji(glyph), glyph)

    def test_marks_change_image(self):
        def picture(**marks):
            return render_picture({'groups': [{'cells': [{'glyph': '🦆', **marks}]}], 'separator': 'none'})
        self.assertNotEqual(picture(), picture(highlight=True))
        self.assertNotEqual(picture(), picture(crossed=True))


if __name__ == '__main__':
    unittest.main()
