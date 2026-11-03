import unittest

from courseware.kit import contract, page
from courseware.tools.check import check_classroom


def shipped(**kw):
    return page.page('认识 & 数一数', '<button id="go">去</button>', '#go{width:60px;height:60px}', 'K.ready({emoji:"🍎",title:"t",sub:"s"});', **kw)


class PageKitTests(unittest.TestCase):
    def test_page_declares_the_fixed_stage_and_passes_the_stage_gate(self):
        html = shipped()
        self.assertIn(f'width:{contract.INTERACTIVE_WIDTH}px;height:{contract.INTERACTIVE_HEIGHT}px', html)
        body = {'stage': {}, 'scenes': [{'type': 'interactive', 'actions': [], 'content': {'html': html}}]}
        codes = {issue['code'] for issue in check_classroom(body)}
        self.assertNotIn('interactive_stage_missing', codes)

    def test_receivers_cover_every_teacher_message(self):
        for message_type in contract.WIDGET_ACTION_TO_MESSAGE.values():
            self.assertIn(message_type, page.JS_HEAD + page.JS_TAIL)

    def test_play_helpers_only_ship_in_the_play_through_variant(self):
        for helper in ('K.sim=', 'K.audit=', 'K.cp=', 'K.check='):
            self.assertNotIn(helper, shipped())
            self.assertIn(helper, shipped(tests=True))
        self.assertIn('K.hud=', shipped())
        self.assertIn('K.ready=', shipped())
        self.assertIn('K.drag=', shipped())

    def test_ids_the_kit_creates_are_reserved(self):
        self.assertTrue({'dots', 'stars', 'hud', 'say', 'ready', 'finish', 'start-btn', 'btn-again'} <= page.reserved_ids())
        self.assertNotIn('go', page.reserved_ids())

    def test_defined_ids_cover_markup_strings_and_dom_calls(self):
        source = ('<div id="a-1"></div><script>b.id="pin-"+i;c.id=\'seat\';d.setAttribute("id","zed");'
                  "e.innerHTML='<i id=\\\"inner\\\"></i>';K.$('#only-a-reference')</script>")
        self.assertEqual(page.defined_ids(source), {'a-1', 'pin-', 'seat', 'zed', 'inner'})

    def test_title_is_escaped_and_structure_is_complete(self):
        html = shipped()
        self.assertIn('<title>认识 &amp; 数一数</title>', html)
        self.assertTrue(html.startswith('<!DOCTYPE html>') and html.endswith('</html>'))
        self.assertEqual(html.count('<script>'), 2)
        self.assertEqual(html, shipped())


if __name__ == '__main__':
    unittest.main()
