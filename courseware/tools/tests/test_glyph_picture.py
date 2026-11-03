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

    def test_rows_layout_and_a_bigger_size(self):
        spec = {'layout': 'rows', 'size': [1280, 640], 'groups': [
            {'cells': [{'glyph': '🦆'}] * 6}, {'cells': [{'glyph': '🔴'}] * 3}, {'cells': [{'glyph': '6'}]}]}
        layout, signs, width, height = _layout_cells(spec)
        self.assertEqual((width, height, signs), (6, 3, []))
        self.assertEqual([(x, y) for x, y, _ in layout], [(i, 0) for i in range(6)] + [(i, 1) for i in range(3)] + [(0, 2)])
        self.assertEqual(Image.open(io.BytesIO(render_picture(spec))).size, (1280, 640))
        # more than eight cells stay on their row in this layout
        self.assertEqual(_layout_cells({'layout': 'rows', 'groups': [{'cells': [{'glyph': 'x'}] * 10}]})[2:], (10, 1))

    def test_invalid_layout_and_size_are_refused(self):
        group = [{'cells': [{'glyph': '1'}]}]
        for bad in ({'layout': 'diagonal'}, {'size': [100, 240]}, {'size': [480]}, {'size': '480x240'}, {'size': [480.0, 240]}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                render_picture({'groups': group, **bad})

    def test_a_glyph_the_font_cannot_draw_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            render_picture({'groups': [{'cells': [{'glyph': '●'}]}]})
        self.assertIn('draws nothing', str(caught.exception))
        for glyph in ('🔴', '6', '🟦'):
            render_picture({'groups': [{'cells': [{'glyph': glyph}]}]})

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
