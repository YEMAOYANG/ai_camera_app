"""Reuse a teacher's recorded lesson line as a replayable game cue."""
import json
import re

from backend.content.textbook_interactive_narration import (
    AUDIO_SCRIPT, CUE_SCHEMA, CUE_SCRIPT, IDENTITY, bind_interactive_audio,
    interactive_cues, without_audio_helper,
)


_OPEN = f'<script type="application/json" id="{CUE_SCRIPT}" data-courseware-reused-audio>'
_MANIFEST = re.compile(re.escape(_OPEN) + r'([^<]*)</script>')


def _speech(body):
    return {line['id']: (scene['id'], line)
            for scene in body['scenes'] if scene['type'] != 'quiz'
            for line in scene.get('actions', []) if line['type'] == 'speech'}


def _line(scene, speech, action_id):
    source = speech.get(action_id) if isinstance(action_id, str) else None
    if not source or source[0] == scene['id']:
        raise ValueError('game audio must reference speech from another teaching scene')
    line = source[1]
    if any(action['type'] == 'speech' and action['text'].strip() == line['text'].strip()
           for action in scene.get('actions', [])):
        raise ValueError('game audio must not duplicate a speech in the same scene')
    return line


def compile_cues(body, requests, teacher_ids):
    if not requests:
        return
    speech = _speech(body)
    for scene in body['scenes']:
        if scene['id'] not in requests:
            continue
        references = requests[scene['id']]
        html = scene['content']['html']
        if interactive_cues(html) or AUDIO_SCRIPT in html:
            raise ValueError('game audio must use the generated narration manifest and player')
        if not isinstance(references, dict) or not 1 <= len(references) <= 120:
            raise ValueError('gameAudio must map cue ids to teacher action ids')
        cues = []
        for cue_id, action_id in references.items():
            if (not isinstance(cue_id, str) or not IDENTITY.fullmatch(cue_id)
                    or not isinstance(action_id, str) or action_id not in teacher_ids):
                raise ValueError('game audio must reference a recorded teacher line')
            line = _line(scene, speech, action_id)
            cues.append({'id': cue_id, 'text': line['text'].strip(), 'speechId': action_id})
        payload = json.dumps({'schemaVersion': CUE_SCHEMA, 'cues': cues}, ensure_ascii=False,
                             separators=(',', ':')).replace('<', r'\u003c')
        scene['content']['html'] = html.replace('</head>', _OPEN + payload + '</script></head>', 1)


def _recordings(body):
    speech = None
    for scene in body.get('scenes', []):
        content = scene.get('content', {})
        html = content.get('html', '')
        if scene.get('type') != 'interactive' or not isinstance(html, str) or _OPEN not in html:
            continue
        manifests = _MANIFEST.findall(html)
        if len(manifests) != 1:
            raise ValueError('invalid game audio manifest')
        if speech is None:
            speech = _speech(body)
        parsed = interactive_cues(html)
        cues = json.loads(manifests[0])['cues']
        if len(cues) != len(parsed):
            raise ValueError('invalid game audio manifest')
        urls = {}
        for cue, validated in zip(cues, parsed):
            line = _line(scene, speech, cue.get('speechId'))
            if validated['text'] != line['text'].strip():
                raise ValueError('game cue text differs from the recorded teacher line')
            urls[validated['id']] = line.get('audioUrl')
        clean = without_audio_helper(html, source_media=True)
        yield content, clean, urls


def bind_recordings(body):
    for content, clean, urls in _recordings(body):
        content['html'] = bind_interactive_audio(clean, urls, body['stage']['id'], source_media=True)


def verify_recordings(body, *, before_voice=False):
    """Remove only exact compiler audio bindings from a pre-voice review comparison."""
    for content, clean, urls in _recordings(body):
        if before_voice and not any(urls.values()):
            expected = clean
        else:
            expected = bind_interactive_audio(clean, urls, body['stage']['id'], source_media=True)
        if content['html'] != expected:
            raise ValueError('game audio does not match its recorded teacher lines')
        if before_voice:
            content['html'] = clean
