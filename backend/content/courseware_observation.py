"""Bounded, ungraded observation cards declared by an authored classroom."""

import json
import re


SNAPSHOT_SCHEMA = 'mira.game.observation.v1'
CARD_ID = 'mira-observation-card'
VIEWS = ('top', 'side')
IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}')
RELEASE_SHA = re.compile(r'[a-f0-9]{64}')
MEDIA = re.compile(r'/api/classroom-media/(?P<classroom>[A-Za-z0-9_-]+)/media/(?:pic-)?(?P<sha>[a-f0-9]{64})\.png')
_SCRIPT = re.compile(
    rf'<script type="application/json" id="{CARD_ID}">([^<]*)</script>'
)


def _fields(value, *names):
    return type(value) is dict and value.keys() == set(names)


def _label(value, limit):
    return isinstance(value, str) and 0 < len(value) <= limit and bool(value.strip())


def _ident(value):
    return isinstance(value, str) and IDENTIFIER.fullmatch(value) is not None


def validate_card(card, *, is_image=lambda path: MEDIA.fullmatch(path) is not None):
    if (not _fields(card, 'title', 'familyTask', 'levels') or not _label(card['title'], 40)
            or not _label(card['familyTask'], 120) or type(card['levels']) is not list
            or not 1 <= len(card['levels']) <= 5):
        raise ValueError('invalid observation card')
    for level in card['levels']:
        if (not _fields(level, 'label', 'trials') or not _label(level['label'], 40)
                or type(level['trials']) is not list or not 1 <= len(level['trials']) <= 8):
            raise ValueError('invalid observation card level')
        trial_ids = set()
        for trial in level['trials']:
            if (not _fields(trial, 'id', 'label', *VIEWS) or not _ident(trial['id'])
                    or trial['id'] in trial_ids or not _label(trial['label'], 40)):
                raise ValueError('invalid observation trial')
            trial_ids.add(trial['id'])
            for view in VIEWS:
                outcomes = trial[view]
                if type(outcomes) is not dict or not 1 <= len(outcomes) <= 8:
                    raise ValueError('invalid observation outcomes')
                for ident, outcome in outcomes.items():
                    if (not _ident(ident) or not _fields(outcome, 'label', 'image')
                            or not _label(outcome['label'], 80)
                            or not isinstance(outcome['image'], str) or not is_image(outcome['image'])):
                        raise ValueError('invalid observation outcome')
    return card


def scene_card(scene):
    content = scene.get('content', {})
    html = content.get('html')
    if scene.get('type') != 'interactive' or not isinstance(html, str):
        return None
    manifests = _SCRIPT.findall(html)
    if not manifests:
        return None
    if len(manifests) != 1 or len(manifests[0]) > 160_000:
        raise ValueError('invalid observation manifest')
    return validate_card(json.loads(manifests[0]))


def project_snapshot(card, scene_id, snapshot):
    """Resolve only allowed outcomes, in lesson order, using authored text and images."""
    if (not _fields(snapshot, 'schemaVersion', 'sceneId', 'kind', 'levels')
            or snapshot['schemaVersion'] != SNAPSHOT_SCHEMA or snapshot['kind'] != 'simulation'
            or snapshot['sceneId'] != scene_id or type(snapshot['levels']) is not list
            or len(snapshot['levels']) != len(card['levels'])):
        raise ValueError('invalid observation snapshot')
    levels = []
    for number, (level, actual) in enumerate(zip(card['levels'], snapshot['levels']), 1):
        if (not _fields(actual, 'level', 'trials') or type(actual['level']) is not int
                or actual['level'] != number or type(actual['trials']) is not list
                or len(actual['trials']) != len(level['trials'])):
            raise ValueError('invalid observation snapshot level')
        observed = {}
        for trial in actual['trials']:
            if (not _fields(trial, 'trialId', *VIEWS) or not _ident(trial['trialId'])
                    or trial['trialId'] in observed or any(not _ident(trial[view]) for view in VIEWS)):
                raise ValueError('invalid observed trial')
            observed[trial['trialId']] = trial
        results = []
        for expected in level['trials']:
            trial = observed.get(expected['id'])
            if trial is None or any(trial[view] not in expected[view] for view in VIEWS):
                raise ValueError('undeclared observation outcome')
            results.append({'label': expected['label'],
                            **{view: dict(expected[view][trial[view]]) for view in VIEWS}})
        levels.append({'label': level['label'], 'trials': results})
    return {'sceneId': scene_id, 'kind': 'simulation', 'title': card['title'],
            'familyTask': card['familyTask'], 'levels': levels}


def report_cards(course, progress, session_id):
    """Read only the observations saved for this report's session and release."""
    if not isinstance(course, dict) or not isinstance(progress, dict):
        return []
    definitions = course.get('observationCards')
    if not isinstance(definitions, dict) or not definitions:
        return []
    release_sha = course.get('releaseSha256')
    classroom = course.get('observationClassroomId')
    if not isinstance(release_sha, str) or not RELEASE_SHA.fullmatch(release_sha) or not _ident(classroom):
        return []
    snapshots = progress.get('activitySnapshots') or {}
    releases = snapshots.get('releases', {}) if isinstance(snapshots, dict) else {}
    scope = releases.get(release_sha) if isinstance(releases, dict) else None
    if (not isinstance(scope, dict) or scope.get('learningSessionId') != session_id
            or scope.get('classroomId') != classroom
            or not isinstance(scope.get('scenes'), dict)):
        return []
    cards = []
    for scene_id, definition in definitions.items():
        saved = scope['scenes'].get(scene_id)
        if not isinstance(saved, dict) or saved.get('contentSha256') != definition['contentSha256']:
            continue
        try:
            card = project_snapshot(definition['card'], scene_id, saved.get('state'))
        except ValueError:
            continue
        cards.append(card)
    return cards


def card_images(cards):
    for card in cards:
        for level in card['levels']:
            for trial in level['trials']:
                for view in VIEWS:
                    yield trial[view]
