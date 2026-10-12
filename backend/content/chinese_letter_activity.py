"""Bounded Chinese alphabet shape pairing; this does not teach letter names."""
from html import escape
import string

from content import textbook_activity_templates as t
from content.textbook_activity_ir import require


def glyph_picture(character):
    require(character in string.ascii_letters and len(character) == 1,
            'letter_glyph_invalid')
    label = ('大写字形 ' if character.isupper() else '小写字形 ') + character
    # The source page uses the single-storey pinyin forms of a and g. Their
    # geometry must not depend on an installed font choosing double-storey forms.
    paths = {
        'N': 'M72 134V42L150 134V42',
        'R': 'M74 134V42H109C164 42 161 88 109 88H74M109 88L154 134',
        'D': 'M73 134V42H101C172 42 172 134 101 134Z',
        'T': 'M67 43H154M111 43V134',
        'L': 'M77 42V133H152',
        'A': 'M64 134 110 42 156 134M84 98H136',
        'B': 'M74 134V42H112C160 42 157 86 111 86H74M111 86C166 86 163 134 112 134H74',
        'G': 'M152 62C119 23 65 40 65 89C65 136 124 152 154 118V95H117',
        'H': 'M73 42V134M150 42V134M73 86H150',
        'E': 'M151 42H75V133H151M75 86H137',
        'Q': 'M153 88C153 25 68 25 68 88C68 151 153 151 153 88ZM124 116 164 149',
        'n': 'M77 134V74M77 99C77 63 143 62 143 99V134',
        'r': 'M85 134V74M85 97C89 77 105 70 130 75',
        'd': 'M143 41V134M143 100C143 62 78 62 78 103C78 143 143 145 143 105',
        't': 'M110 46V116Q110 140 137 131M82 79H142',
        'b': 'M77 41V134M77 99C77 62 143 62 143 103C143 143 77 144 77 104',
        'h': 'M77 41V134M77 99C77 64 143 62 143 101V134',
        'e': 'M80 99H146C146 64 78 65 78 102C78 142 127 145 145 125',
        'q': 'M143 74V163M143 99C143 62 78 62 78 103C78 143 143 144 143 104',
        'a': 'M139 74V132M139 97C139 61 79 60 79 104C79 143 139 143 139 106',
        'g': 'M139 73V131C139 161 113 167 88 151M139 96C139 62 79 61 79 100C79 138 139 139 139 103',
        'l': 'M110 40V132',
    }
    glyph = ('<path d="' + paths[character] + '" fill="none" stroke="#385f53" '
             'stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>'
             if character in paths else
             '<text x="110" y="132" text-anchor="middle" font-family="Arial,sans-serif" '
             'font-size="125" fill="#385f53">' + character + '</text>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 180" '
            'role="img" aria-label="' + label + '"><title>' + label + '</title>'
            '<rect x="8" y="8" width="204" height="164" rx="18" fill="#fff9e7"/>'
            '<path d="M28 134h164" stroke="#c8d4bf" stroke-width="2"/>'
            + glyph + '</svg>')


def validate_scene(scene, assets, scope):
    expected = scope.get('letterCasePairs', {})
    rows = scene.get('rounds', [])
    require(3 <= len(rows) <= 26 and len(rows) == len(expected)
            and len({r.get('uppercase') for r in rows}) == len(rows)
            and {r.get('uppercase'): r.get('lowercase') for r in rows} == expected
            and set(scene.get('activityGoalIds', [])) == {'letter_case_matching'},
            'letter_case_scope_changed')
    require(all(k in string.ascii_uppercase and len(k) == 1 and v == k.lower()
                for k, v in expected.items()), 'letter_case_pair_invalid')
    targets = {r['targetAssetId']: r['lowercase'] for r in rows}
    require(len(targets) == len(rows), 'letter_case_target_reused')
    for row in rows:
        options = row['optionAssetIds']
        require(row.get('mode') == 'letter_case_shape_matching'
                and len(options) == len(set(options)) == 3
                and row['targetAssetId'] in options and set(options) <= set(targets),
                'letter_case_choices_invalid')
        require(assets[row['uppercaseAssetId']] == glyph_picture(row['uppercase'])
                and all(assets[key] == glyph_picture(targets[key]) for key in options),
                'letter_case_glyph_changed')


def letter_scene(scene, assets):
    keys = list(dict.fromkeys(k for r in scene['rounds'] for k in r['optionAssetIds']))
    crops = {r['targetAssetId']: assets[r['uppercaseAssetId']] for r in scene['rounds']}
    body = ('<div class="target-row"><button type="button" id="source" class="target" '
            'aria-label="点大写字形，再找小写伙伴">' + crops[scene['rounds'][0]['targetAssetId']]
            + '</button><div id="pair" class="pair" aria-live="polite"></div>'
            '<div id="detail" class="picture-detail" hidden></div></div>')
    body += '<div class="choices" id="choices">' + ''.join(
        t.picture_button('option-' + k, k, assets[k], extra='data-option="' + escape(k) + '"')
        for k in keys) + '</div>'
    body += '<div class="progress" aria-label="字形配对进度">' + ''.join(
        '<i data-progress="' + str(i) + '"></i>' for i in range(len(scene['rounds']))) + '</div>'
    body += '<div class="tools">' + t.button('start', '开始配对', 'start', 'data-cancel')
    body += t.button('replay', '重听', 'replay', 'data-cancel') + t.button('reset', '重新配对', 'reset', 'data-cancel')
    body += t.button('hint', '看看一对', 'hint') + t.button('next', '下一对', 'next') + '</div>'
    body += '''<style>
.target-row{flex-wrap:nowrap;gap:10px}.target{width:144px;height:120px;flex-shrink:0}
.pair{min-height:100px;padding:6px}.pair>svg{width:90px;height:90px}
#pair:has(~ #detail:not([hidden])){display:none}
#detail{display:flex;align-items:center;gap:6px;max-width:none;margin:0;padding:6px;border:3px solid #be8b47;border-radius:12px}
#detail[hidden]{display:none}#detail svg{width:90px;height:90px}
.choices>button{min-height:104px;padding:6px}.choices>button svg{max-height:110px}
.progress{gap:6px;flex-wrap:wrap;margin:8px auto}.progress i{width:16px;height:16px;border-width:2px}
.tools{gap:4px}.tools button{min-width:56px;min-height:56px;padding:8px}.tools button span{display:none}
@media(max-width:420px){.target-row{gap:5px}.target{width:108px;height:100px}.pair>svg,#detail svg{width:68px;height:78px}.pair .feedback-mark{width:30px;height:30px}.choices>button{min-height:86px}.choices>button svg{max-height:86px}}
</style>'''
    config = {'rounds': scene['rounds'], 'crops': crops, 'assets': {k: assets[k] for k in keys},
              'intro': scene['initialCueId'], 'retry': scene['retryCueId'], 'hint': scene['hintCueId'],
              'reset': scene['resetCueId'], 'complete': scene['completeCueId']}
    code = t.VISIBLE_MATCH_CODE.replace('CONFIG', t.js(config))
    anchor = 'detail.innerHTML=source.innerHTML;detail.hidden=false;'
    require(code.count(anchor) == 1, 'letter_hint_template_changed')
    code = code.replace(anchor, 'assisted=true;detail.innerHTML=source.innerHTML+'
                        'config.assets[config.rounds[round].targetAssetId];detail.hidden=false;')
    progress = "function updateProgress(){document.querySelectorAll('[data-progress]').forEach((e,i)=>{const done=i<round||(i===round&&matched&&feedbackReady);e.classList.toggle('done',done);e.setAttribute('aria-label',done?'这一对已配好':'这一对还可以试');});}\n"
    return t.scene_html(scene, body, progress + code)
