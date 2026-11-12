"""Replay an authentic G7 review after a supported visual-only correction."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re

from courseware.tools import verify, verify_delta


EVIDENCE_SCHEMA = 'mira.courseware.verification-presentation-evidence.v1'
STATIC_ANCHOR = 'static-anchor-compensation'
HANDOFF_CLEANUP = 'handoff-highlight-cleanup'
PLAY_LEFT, PLAY_TOP = 24, 86
# Pin the compiled kit/classic stylesheet that defines the coordinate origin.
# A later kit revision needs a separate reviewed layout profile.
_FRAME_STYLE_BYTES = 10296
_FRAME_STYLE_SHA256 = 'b043a6ce96728d3dc0a0f77e1ed574cd1ee573cbe6f7c7741193595c7b9bcf98'
_READY_PICTURE_STYLE = re.compile(
    r'\s*(?:#cv\.classic-arcade #ready \.pic\s*\{\s*object-fit:\s*contain;'
    r'\s*background:\s*#[0-9a-fA-F]{6};\s*\}\s*)?'
)
_PLAY_OPEN = '<div id="cv"><div id="play">'
_PLAY_CLOSE = '</div></div><script>'
_ANCHOR = re.compile(
    r'<(?P<tag>div|span) id="(?P<id>[A-Za-z][A-Za-z0-9_-]{0,127})"'
    r'(?P<fixed> class="g-anchor")?(?P<hidden> aria-hidden="true")?'
    r'(?: style="left:(?P<left>0|[1-9][0-9]{0,3})px;top:(?P<top>0|[1-9][0-9]{0,3})px;'
    r'width:[1-9][0-9]{0,3}px;height:[1-9][0-9]{0,3}px")?></(?P=tag)>'
)
_HANDOFF_WRAPPER = """
const setGameState = K.onState;
K.onState = (state, content) => {
  if (state?.demo === false) {
    K.$$('.teach-hl').forEach(element => element.classList.remove('teach-hl'));
  }
  return setGameState.call(K, state, content);
};
"""
# These compiled profiles pin the shared highlight, game reset, and template
# code independently of later changes to the kit on disk.
_HANDOFF_RUNTIME_SHA256 = {
    'magnetMarbles': '64681e5cf43646e4694e618a1c58b9f177b7e5eb758ba997c934f70c42f2f834',
    'listenDelivery': '5528f178d5ea0a0d8e6a381246f99b874f7ad8cb7581406a5227091903a5214d',
}
_HANDOFF_FRAME = re.compile(
    r'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">'
    r'<meta name="viewport" content="width=device-width,initial-scale=1">'
    r'<title>[^<]*</title><style>(?P<css>[^<]*)</style>'
    r'(?:<script type="application/json" id="mira-narration-cues" data-courseware-reused-audio>'
    r'[^<]*</script>)?</head><body>'
    + re.escape(_PLAY_OPEN) + r'(?P<play>.*?)' + re.escape(_PLAY_CLOSE)
    + r'(?P<runtime>.*?)</script><script>(?P<script>[^<]+)</script></body></html>',
    re.S,
)
_HANDOFF_ANCHOR = re.compile(
    r'<span id="(?P<id>[A-Za-z][A-Za-z0-9_-]{0,127})"'
    r'(?: class="(?P<fixed>g-anchor)")? aria-hidden="true"'
    r'(?: style="left:\d{1,4}px;top:\d{1,4}px;width:\d{1,4}px;height:\d{1,4}px")?></span>'
)
_HANDOFF_GAME_CALL = re.compile(r'^K\.game\(K\.gameTemplates\.([A-Za-z][A-Za-z0-9]*)\(\{', re.M)
_HANDOFF_STRING = re.compile(r"""(?:'[^'\r\n]*'|"[^"\r\n]*")""")
_HANDOFF_CONFIG_CALL = re.compile(
    r'K\.ready\(|K\.game\(K\.gameTemplates\.[A-Za-z][A-Za-z0-9]*\('
    r'|Object\.keys\([A-Za-z][A-Za-z0-9]*\)\.map\(([A-Za-z][A-Za-z0-9]*) => \[\1, \1\]\)'
)
_HANDOFF_CUSTOM_BEHAVIOR = re.compile(
    r"""[("']|//|/\*|\*/|\x60|\b(?:K|document|window|globalThis|this|new|function|class|import|export"""
    r'|MutationObserver|eval|Function|prototype|constructor)\b'
)


def _compensate(scene, current_html):
    prior_html = scene['content']['html']
    if (prior_html.count(_PLAY_OPEN) != 1 or prior_html.count(_PLAY_CLOSE) != 1
            or len(re.findall(r'<style(?=[\s>])', prior_html, flags=re.I)) != 1
            or re.search(r'<link(?=[\s>])', prior_html, flags=re.I)
            or prior_html.count('<style>') != 1 or prior_html.count('</style>') != 1):
        raise ValueError('Unsupported presentation frame')
    css = prior_html.split('<style>', 1)[1].split('</style>', 1)[0].encode('utf-8')
    frame, extra = css[:_FRAME_STYLE_BYTES], css[_FRAME_STYLE_BYTES:]
    if (sha256(frame).hexdigest() != _FRAME_STYLE_SHA256
            or not _READY_PICTURE_STYLE.fullmatch(extra.decode('utf-8'))):
        raise ValueError('Presentation frame styles differ from the supported layout')
    lead, rest = prior_html.split(_PLAY_OPEN)
    fragment, tail = rest.split(_PLAY_CLOSE)
    # Accept only an anchor-only play fragment. Every matched element is
    # empty and a direct child, with no interactive markup or attributes.
    if _ANCHOR.sub('', fragment).strip():
        raise ValueError('The presentation frame must contain only supported empty anchors')
    highlights = [action.get('target') for action in scene['actions'] if action.get('type') == 'widget_highlight']
    corrected = 0

    def replace_anchor(match):
        nonlocal corrected
        name = match['id']
        left, top = match['left'], match['top']
        if match['tag'] == 'div':
            if not match['fixed'] or match['hidden']:
                raise ValueError('Unsupported presentation div anchor')
        elif not match['hidden'] or bool(match['fixed']) != (left is not None):
            raise ValueError('Unsupported presentation span anchor')
        # Unstyled placeholders stay byte-identical in the reconstructed HTML.
        if left is None or int(left) < PLAY_LEFT or int(top) < PLAY_TOP:
            return match[0]
        old_position = f'left:{left}px;top:{top}px'
        new_position = f'left:{int(left) - PLAY_LEFT}px;top:{int(top) - PLAY_TOP}px'
        adjusted = match[0].replace(old_position, new_position, 1)
        if current_html.count(adjusted) != 1:
            return match[0]
        # Names are unique in the old HTML, including its scripts and styles.
        occurrences = re.findall(rf'(?<![\w-]){re.escape(name)}(?![\w-])', prior_html)
        if len(occurrences) != 1 or highlights.count('#' + name) != 1:
            raise ValueError('An adjusted anchor must uniquely belong to a teacher highlight')
        corrected += 1
        return adjusted

    new_fragment = _ANCHOR.sub(replace_anchor, fragment)
    if not corrected or lead + _PLAY_OPEN + new_fragment + _PLAY_CLOSE + tail != current_html:
        raise ValueError('Presentation changes must be exact static anchor compensation')
    return current_html


def _demo_reset(action, demo):
    state = action.get('state')
    return (action.get('type') == 'widget_setState' and isinstance(state, dict)
            and set(state) == {'demo', 'level', 'pause'} and state['demo'] is demo and state['pause'] is demo
            and type(state['level']) is int and state['level'] == 1)


def _clear_handoff_highlights(scene, current_html):
    prior_html = scene['content']['html']
    frame = _HANDOFF_FRAME.fullmatch(prior_html)
    if (frame is None or 'setGameState' in prior_html
            or sha256(frame['css'].encode('utf-8')).hexdigest() != _FRAME_STYLE_SHA256):
        raise ValueError('Unsupported handoff presentation frame')
    script = frame['script']
    calls = _HANDOFF_GAME_CALL.findall(script)
    config = _HANDOFF_CONFIG_CALL.sub('', _HANDOFF_STRING.sub('', script))
    if (len(calls) != 1 or script.count('K.game(') != 1 or not script.startswith('K.ready({')
            or not script.endswith('}));\n') or 'teach-hl' in script or '\\' in script
            or _HANDOFF_CUSTOM_BEHAVIOR.search(config)
            or sha256(frame['runtime'].encode('utf-8')).hexdigest() != _HANDOFF_RUNTIME_SHA256.get(calls[0])):
        raise ValueError('Handoff cleanup requires the supported shared game and an unwrapped game configuration')

    anchors = list(_HANDOFF_ANCHOR.finditer(frame['play']))
    anchor_ids = {anchor['id'] for anchor in anchors}
    fixed = {'#' + anchor['id'] for anchor in anchors if anchor['fixed']}
    if (_HANDOFF_ANCHOR.sub('', frame['play']).strip() or len(anchor_ids) != len(anchors)):
        raise ValueError('Handoff cleanup requires unique empty presentation anchors')
    actions = scene['actions']
    if len(actions) < 2 or not _demo_reset(actions[0], True) or not _demo_reset(actions[-1], False):
        raise ValueError('Handoff cleanup requires the existing teacher demo and final child reset')
    targets = {action.get('target') for action in actions[:-1] if action.get('type') == 'widget_highlight'}
    if not targets or not targets <= fixed:
        raise ValueError('Handoff cleanup requires existing teacher highlights on fixed anchors')

    end = frame.end('script')
    if prior_html[:end] + _HANDOFF_WRAPPER + prior_html[end:] != current_html:
        raise ValueError('Presentation changes must be the exact handoff highlight cleanup')
    return current_html


def _require_presentation_change(prior, body, change_kind):
    change = {STATIC_ANCHOR: _compensate, HANDOFF_CLEANUP: _clear_handoff_highlights}[change_kind]
    expected = verify._evidence_body(prior)
    current = verify._evidence_body(body)
    changed = False
    if len(expected['scenes']) != len(current['scenes']):
        raise ValueError('Presentation scene count changed')
    for old, new in zip(expected['scenes'], current['scenes']):
        if old.get('type') != 'interactive' or new.get('type') != 'interactive':
            continue
        html = new['content']['html']
        if old['content']['html'] != html:
            old['content']['html'] = change(old, html)
            changed = True
    if not changed or expected != current:
        raise ValueError('Body differs beyond the allowed presentation correction')


def _review(body, notes, media, prior, model, effort, change_kind):
    old_requests, old_pictures, original, original_receipt = verify_delta._validate_prior(prior, notes, model, effort)
    if original_receipt['disagreements']:
        raise ValueError('Presentation replay requires a passing original independent review')
    _require_presentation_change(prior['body'], body, change_kind)
    requests = verify.build_requests(body, notes, media=media, teaching=True, strict_media=True)
    pictures = verify_delta._read_pictures(requests, media)
    if ([verify_delta._request_digest(request, old_pictures) for request in old_requests]
            != [verify_delta._request_digest(request, pictures) for request in requests]
            or [request['items'] for request in old_requests] != [request['items'] for request in requests]):
        raise ValueError('Independent review requests or quiz images changed')
    verify_delta._verify_presentation_media(body, media, pictures)
    input_sha = verify._evidence_input_hash(body, requests, pictures)
    receipt = verify.build_receipt(body, notes, requests, original['verdicts'], verify_delta._answers(body),
                                   model=model, effort=effort, ran_at=original['ranAt'])
    return receipt, input_sha


def _referenced_receipt(receipt, evidence):
    receipt['reusedEvidence'] = {'schemaVersion': EVIDENCE_SCHEMA, 'sha256': verify.body_hash(evidence),
                                 'inputSha256': evidence['inputSha256'],
                                 'reviewedBodySha256': verify.body_hash(evidence['prior']['body'])}
    if 'changeKind' in evidence:
        receipt['reusedEvidence']['changeKind'] = evidence['changeKind']
    return receipt


def replay(body, notes, media, evidence, *, model=verify.VERIFIER_MODEL, effort=verify.VERIFIER_EFFORT):
    fields = {'schemaVersion', 'prior', 'inputSha256'}
    if (not isinstance(evidence, dict) or evidence.get('schemaVersion') != EVIDENCE_SCHEMA
            or not (set(evidence) == fields
                    or set(evidence) == fields | {'changeKind'} and evidence['changeKind'] == HANDOFF_CLEANUP)):
        raise ValueError('Malformed presentation verification evidence')
    receipt, input_sha = _review(body, notes, media, evidence['prior'], model, effort,
                                 evidence.get('changeKind', STATIC_ANCHOR))
    if evidence['inputSha256'] != input_sha:
        raise ValueError('Wrong current verifier inputs for presentation replay')
    return _referenced_receipt(receipt, evidence)


def create_proof(*, body, notes, media, prior_body, prior_media, prior_evidence, prior_evidence_sha256,
                 model=verify.VERIFIER_MODEL, effort=verify.VERIFIER_EFFORT, change_kind=STATIC_ANCHOR):
    if change_kind not in (STATIC_ANCHOR, HANDOFF_CLEANUP):
        raise ValueError('Unsupported presentation change kind')
    old_requests = verify.build_requests(prior_body, notes, media=prior_media, teaching=True, strict_media=True)
    old_pictures = verify_delta._read_pictures(old_requests, prior_media)
    verify_delta._verify_presentation_media(prior_body, prior_media, old_pictures)
    prior = {'body': prior_body, 'evidenceUtf8': prior_evidence.decode('utf-8'),
             'evidenceSha256': prior_evidence_sha256,
             'pictures': {Path(path).name: old_pictures[path] for path in sorted(old_pictures)}}
    receipt, input_sha = _review(body, notes, media, prior, model, effort, change_kind)
    evidence = {'schemaVersion': EVIDENCE_SCHEMA, 'prior': prior, 'inputSha256': input_sha}
    if change_kind == HANDOFF_CLEANUP:
        evidence['changeKind'] = change_kind
    return _referenced_receipt(receipt, evidence), evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('body', 'notes', 'prior-body', 'prior-evidence', 'out', 'save-evidence'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('media', 'prior-media'):
        parser.add_argument('--' + name, type=Path)
    for name in ('prior-evidence-sha256', 'expected-input-sha256'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--model', default=verify.VERIFIER_MODEL)
    parser.add_argument('--effort', default=verify.VERIFIER_EFFORT)
    parser.add_argument('--change-kind', choices=(STATIC_ANCHOR, HANDOFF_CLEANUP), default=STATIC_ANCHOR)
    args = parser.parse_args(argv)
    try:
        outputs = (args.out, args.save_evidence)
        if len({path.resolve() for path in outputs}) != 2 or any(os.path.lexists(path) for path in outputs):
            raise ValueError('Presentation replay needs two new, distinct output paths')
        receipt, evidence = create_proof(
            body=verify_delta._read_body(args.body), notes=json.loads(args.notes.read_text(encoding='utf-8')),
            media=args.media or args.body.parent / 'media', prior_body=verify_delta._read_body(args.prior_body),
            prior_media=args.prior_media or args.prior_body.parent / 'media',
            prior_evidence=args.prior_evidence.read_bytes(), prior_evidence_sha256=args.prior_evidence_sha256,
            model=args.model, effort=args.effort, change_kind=args.change_kind)
        if evidence['inputSha256'] != args.expected_input_sha256:
            raise ValueError('Current input does not match the approved SHA')
        verify_delta._write_json(args.save_evidence, evidence)
        verify_delta._write_json(args.out, receipt)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, 'Presentation verification failed: %s\n' % exc)
    print('Replayed the original independent review for ' + args.change_kind + '.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
