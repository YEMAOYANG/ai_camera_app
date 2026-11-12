"""Proof of approved Classic controls, built locally and checked on delivery."""
from datetime import date
import hashlib
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from content.textbook_catalog import canonical, digest


SCHEMA = 'mira.textbook.student-activity-controls.v1'
SOURCE_PROOF_SCHEMA = 'mira.textbook.student-activity-controls.source-proof.v2'
FIELD = 'studentActivityControls'
_TEMPLATES = {'sortingDepot': 1, 'bubbleMaze': 1}
_SOURCE_ONLY_TEMPLATES = frozenset(('magnetMarbles', 'platformHop', 'shutterScout', 'listenDelivery',
                                    'fallingTiles', 'compareSnake', 'slideMerge', 'fireflySwing',
                                    'orchardCatch', 'wordBubbles'))
_SOURCE_TEMPLATES = frozenset(_TEMPLATES) | _SOURCE_ONLY_TEMPLATES
_ROOT = Path(__file__).resolve().parents[2] / 'courseware'
_ID = re.compile(r'[a-z0-9][a-z0-9-]{0,127}')
_SHA = re.compile(r'[a-f0-9]{64}')
_HASH_FIELDS = ('sourceContentSha256', 'sourceScriptSha256', 'templateVersionSha256')


def _require(condition, code='student_activity_controls_invalid'):
    if not condition:
        raise ValueError(code)


def _read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def _html_sha(scene):
    content = scene.get('content', {})
    html = content.get('html')
    _require(scene.get('type') == content.get('type') == 'interactive'
             and isinstance(html, str) and bool(html.strip()))
    return hashlib.sha256(html.encode()).hexdigest()


def _binding_fields(binding):
    return {'editionId': binding['editionId'], 'revisionId': binding['alignmentRevisionId'],
            'nodeId': binding['nodeId'], 'teachingRevision': binding['teachingRevision']}


def _game_declarations(brief, binding):
    expected_binding = _binding_fields(binding)
    _require(isinstance(brief, dict) and brief.get('schemaVersion') == 'mira.courseware.brief.v1'
             and isinstance(brief.get('binding'), dict)
             and all(brief['binding'].get(key) == value for key, value in expected_binding.items()))
    games = brief.get('games')
    _require(isinstance(games, list) and 0 < len(games) <= 60)
    declarations = {}
    for game in games:
        _require(isinstance(game, dict))
        page, template, version, approved = (game.get(k) for k in ('page', 'template', 'version', 'ownerApprovedOn'))
        _require(isinstance(page, str) and _ID.fullmatch(page) and page not in declarations)
        _require(isinstance(template, str) and type(version) is int and _TEMPLATES.get(template) == version,
                 'student_activity_controls_template_unapproved')
        _require(game.get('entryPoint') == 'K.gameTemplates.' + template and isinstance(approved, str))
        try:
            _require(date.fromisoformat(approved).isoformat() == approved)
        except ValueError as exc:
            raise ValueError('student_activity_controls_invalid') from exc
        declarations[page] = {'page': page, 'template': template, 'version': version, 'ownerApprovedOn': approved}
    return declarations


def _uses_v1_proof(brief):
    games = brief.get('games')
    binding = brief.get('binding')
    fields = {'page', 'template', 'version', 'entryPoint', 'ownerApprovedOn'}
    return (isinstance(binding, dict) and 'teachingRevision' in binding
            and isinstance(games, list) and bool(games)
            and all(isinstance(game, dict) and fields <= game.keys()
                    and not (isinstance(game['template'], str)
                             and game['template'] in _SOURCE_ONLY_TEMPLATES
                             and game['entryPoint'] == 'K.gameTemplates.' + game['template'])
                    for game in games))


def _trusted_source(source_id, brief, *, allow_alias):
    parent = _ROOT / 'lessons'
    source = parent / source_id
    if allow_alias and not source.exists() and not source.is_symlink():
        # Some frozen bodies use an older playback namespace. Match the full
        # brief in the trusted source tree, then replay using that namespace.
        expected = canonical(brief)
        candidates = []
        for path in parent.glob('*/brief.json'):
            if (not _ID.fullmatch(path.parent.name) or path.resolve() != path
                    or not (path.parent / 'lesson.json').is_file()):
                continue
            try:
                if canonical(_read(path)) == expected:
                    candidates.append(path.parent)
            except (OSError, ValueError):
                continue
        _require(len(candidates) == 1, 'student_activity_controls_source_unavailable')
        source = candidates[0]
    _require(source.is_dir() and source.resolve() == source, 'student_activity_controls_source_unavailable')
    _require(not any((source / name).is_symlink() for name in ('brief.json', 'lesson.json')),
             'student_activity_controls_source_unavailable')
    _require(canonical(_read(source / 'brief.json')) == canonical(brief), 'student_activity_controls_brief_changed')
    return source


def _source_games(source, lesson, catalog):
    from courseware.kit import game, game_templates

    kit = _ROOT / 'kit/game_templates'
    classic = (kit / 'classic.js').read_text(encoding='utf-8')
    template_scripts = {name: (kit / (name + '.js')).read_bytes() for name in _SOURCE_TEMPLATES}
    compiled_templates = {name: '\n'.join((classic, raw.decode())) for name, raw in template_scripts.items()}
    for item in lesson['scenes']:
        if item.get('type') != 'interactive':
            continue
        page, outline = item['page'], item['key']
        _require(_ID.fullmatch(page) and _ID.fullmatch(outline))
        script_path = source / 'pages' / (page + '.js')
        _require(script_path.resolve() == script_path, 'student_activity_controls_source_unavailable')
        script = script_path.read_text(encoding='utf-8')
        try:
            compiled = game_templates.javascript(script)
        except ValueError as exc:
            raise ValueError('student_activity_controls_template_mismatch') from exc
        matching = [name for name, js in compiled_templates.items() if compiled == js]
        _require(game.uses_game(script) and len(matching) == 1, 'student_activity_controls_template_mismatch')
        template = matching[0]
        versions = [entry for template_row in catalog['templates'] if template_row['id'] == template
                    for entry in template_row['versions']
                    if entry.get('status') == '可用' and entry.get('entryPoint') == 'K.gameTemplates.' + template
                    and entry.get('source') == f'courseware/kit/game_templates/{template}.js']
        _require(len(versions) == 1 and type(versions[0].get('version')) is int and versions[0]['version'] == 1,
                 'student_activity_controls_template_unapproved')
        version = versions[0]
        yield {'page': page, 'outlineId': outline, 'template': template, 'version': version['version'],
               'ownerApprovedOn': version.get('ownerApprovedOn'),
               'sourceScriptSha256': hashlib.sha256(script.encode()).hexdigest(),
               'templateVersionSha256': digest(version),
               'templateSourceSha256': hashlib.sha256(template_scripts[template]).hexdigest()}


def _check_source_brief(brief, binding, rows, orders, catalog_sha):
    _require(brief.get('schemaVersion') == 'mira.courseware.brief.v1')
    expected_binding = _binding_fields(binding)
    for field in ('binding', 'lesson'):
        declared = brief.get(field, {})
        if field == 'lesson' and isinstance(declared, str):
            continue  # Some older briefs use this field for the title.
        _require(isinstance(declared, dict))
        _require(all(declared.get(key, value) == value for key, value in expected_binding.items()))

    def match(game, outer=None):
        _require(isinstance(game, dict))
        selectors = {'page': 'page', 'scene': 'outlineId', 'sceneId': 'sceneId', 'key': 'outlineId'}
        fields = {} if outer is None else {k: outer[k] for k in selectors if k in outer}
        order = fields.pop('page') if type(fields.get('page')) is int else None
        matches = [row for row in rows if (order is None or orders[row['sceneId']] == order)
                   and all(game.get(key, row[field]) == row[field]
                           and fields.get(key, row[field]) == row[field] for key, field in selectors.items())]
        _require(len(matches) == 1, 'student_activity_controls_page_unmatched')
        row = matches[0]
        template = row['template']
        _require(game.get('template', template) in (template, template + '@1')
                 and type(game.get('version', 1)) is int and game.get('version', 1) == 1
                 and game.get('entryPoint', 'K.gameTemplates.' + template) == 'K.gameTemplates.' + template
                 and all(game.get(k, row[k]) == row[k] for k in ('ownerApprovedOn', 'templateSourceSha256'))
                 and game.get('catalogSha256', catalog_sha) == catalog_sha,
                 'student_activity_controls_template_mismatch')
        return row['sceneId']

    authoring = brief.get('authoring', {})
    _require(isinstance(authoring, dict))
    for declarations in (brief.get('games', []), authoring.get('games', [])):
        _require(isinstance(declarations, list) and len(declarations) <= 60)
        seen = set()
        for game in declarations:
            scene_id = match(game)
            _require(scene_id not in seen, 'student_activity_controls_page_unmatched')
            seen.add(scene_id)
    for field in ('pageSequence', 'pageOrder', 'pages'):
        sequence = brief.get(field, [])
        if not isinstance(sequence, list):
            continue
        for item in sequence:
            if isinstance(item, dict) and 'game' in item:
                match(item['game'], outer=item)


def _replay(source, source_id, created, body, media, *, exact):
    from courseware.tools import build

    files = {}
    prefix = f'/api/classroom-media/{source_id}/media/'
    for scene in body['scenes']:
        for action in scene['actions']:
            if action.get('type') != 'speech':
                continue
            url = action.get('audioUrl', '')
            _require(isinstance(url, str) and url.startswith(prefix))
            name = url[len(prefix):]
            _require(Path(name).name == name and name.endswith('.wav') and name in media
                     and action['id'] not in files)
            files[action['id']] = name
    with TemporaryDirectory(prefix='mira-controls-replay-') as directory:
        work = Path(directory)
        draft = build.prepare(source, work, stage_id=source_id, now_ms=created)
        for name in set(files.values()):
            (work / 'media' / name).write_bytes(media[name])
        replay = build.finish(draft, work, files)
        _require(canonical(replay) == canonical(body), 'student_activity_controls_body_changed')
        if exact:
            replay_media = {p.name: p for p in (work / 'media').iterdir()}
            _require(replay_media.keys() == media.keys() and all(
                replay_media[name].read_bytes() == raw for name, raw in media.items()),
                'student_activity_controls_media_changed')


def _media_sha(inventory):
    return digest(sorted(inventory, key=lambda row: row['sourceName']))


def _source_proof(source, source_id, created, brief, body, media, binding):
    lesson = _read(source / 'lesson.json')
    catalog_path = _ROOT / 'kit/game_templates/catalog.json'
    catalog_sha = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
    by_id = {scene['id']: scene for scene in body['scenes'] if scene['type'] == 'interactive'}
    rows = []
    for game in _source_games(source, lesson, _read(catalog_path)):
        scene_id = 'scene-' + game['outlineId']
        scene = by_id.get(scene_id, {})
        _require(scene.get('outlineId') == game['outlineId'], 'student_activity_controls_page_unmatched')
        rows.append({**game, 'sceneId': scene_id, 'sourceContentSha256': _html_sha(scene)})
    _check_source_rows(rows, by_id)
    _check_source_brief(brief, binding, rows, {sid: scene['order'] for sid, scene in by_id.items()}, catalog_sha)
    inventory = []
    for name, raw in media.items():
        sha = hashlib.sha256(raw).hexdigest()
        _require(Path(name).stem.endswith(sha), 'student_activity_controls_media_changed')
        inventory.append({'sourceName': name, 'sha256': sha})
    _replay(source, source_id, created, body, media, exact=True)
    return {'schemaVersion': SOURCE_PROOF_SCHEMA, 'brief': brief, 'bodySha256': digest(body), 'scenes': rows,
            'sourceStageId': source_id, 'catalogSha256': catalog_sha, 'mediaSha256': _media_sha(inventory)}


def compile_evidence(request, brief, body, media, binding):
    """Resolve the operator's source locally and replay the existing compiler.

    A package can request controls. It cannot supply its own provenance or
    choose a source directory. No authored HTML is inspected for eligibility.
    """
    from courseware.kit import game, game_templates
    from courseware.tools import build

    _require(request is True and isinstance(brief, dict))
    legacy = _uses_v1_proof(brief)
    declarations = _game_declarations(brief, binding) if legacy else None
    stage = body['stage']
    source_id, created = stage['id'], stage.get('createdAt')
    _require(isinstance(source_id, str) and _ID.fullmatch(source_id) and type(created) is int and created > 0)
    try:
        source = _trusted_source(source_id, brief, allow_alias=not legacy)
        if not legacy:
            return _source_proof(source, source_id, created, brief, body, media, binding)
        lesson = _read(source / 'lesson.json')
        catalog = _read(_ROOT / 'kit/game_templates/catalog.json')
        scenes = []
        for page, declaration in declarations.items():
            matches = [item for item in lesson['scenes'] if item.get('type') == 'interactive' and item.get('page') == page]
            _require(len(matches) == 1, 'student_activity_controls_page_unmatched')
            template = declaration['template']
            versions = [entry for item in catalog['templates'] if item['id'] == template
                        for entry in item['versions'] if entry['version'] == declaration['version']]
            _require(len(versions) == 1 and versions[0].get('status') == '可用'
                     and versions[0].get('ownerApprovedOn') == declaration['ownerApprovedOn']
                     and versions[0].get('entryPoint') == 'K.gameTemplates.' + template
                     and versions[0].get('source') == f'courseware/kit/game_templates/{template}.js',
                     'student_activity_controls_template_unapproved')
            script_path = source / 'pages' / (page + '.js')
            _require(script_path.resolve() == script_path, 'student_activity_controls_source_unavailable')
            script = script_path.read_text(encoding='utf-8')
            kit = _ROOT / 'kit/game_templates'
            expected_js = '\n'.join((kit / (name + '.js')).read_text(encoding='utf-8') for name in ('classic', template))
            _require(game.uses_game(script) and game_templates.javascript(script) == expected_js,
                     'student_activity_controls_template_mismatch')
            scene_id = 'scene-' + matches[0]['key']
            selected = [scene for scene in body['scenes'] if scene.get('id') == scene_id]
            _require(len(selected) == 1 and selected[0].get('outlineId') == matches[0]['key'],
                     'student_activity_controls_page_unmatched')
            scenes.append({**declaration, 'sceneId': scene_id, 'outlineId': matches[0]['key'],
                           'sourceContentSha256': _html_sha(selected[0]),
                           'sourceScriptSha256': hashlib.sha256(script.encode()).hexdigest(),
                           'templateVersionSha256': digest(versions[0])})

        _replay(source, source_id, created, body, media, exact=False)
    except (OSError, build.BuildError) as exc:
        raise ValueError('student_activity_controls_source_unavailable') from exc
    return {'schemaVersion': SCHEMA, 'brief': brief, 'bodySha256': digest(body), 'scenes': scenes}


def descriptors(evidence, classroom):
    """Describe only registered scenes, hashing HTML after release conversion."""
    result = []
    seen = set()
    for row in evidence['scenes']:
        scene_id = row['sceneId']
        _require(isinstance(scene_id, str) and _ID.fullmatch(scene_id) and scene_id not in seen
                 and isinstance(row['outlineId'], str) and scene_id == 'scene-' + row['outlineId'])
        matches = [scene for scene in classroom['scenes'] if scene.get('id') == scene_id]
        _require(len(matches) == 1 and matches[0].get('stageId') == classroom['id']
                 and matches[0].get('outlineId') == row['outlineId'])
        seen.add(scene_id)
        result.append({'sceneId': scene_id, 'template': row['template'], 'version': row['version'],
                       'contentSha256': _html_sha(matches[0])})
    return {'schemaVersion': SCHEMA, 'scenes': result}


def _check_source_rows(rows, by_id):
    _require(isinstance(rows, list) and 0 < len(rows) <= 60 and len(rows) == len(by_id))
    seen = set()
    for row in rows:
        fields = {'page', 'template', 'version', 'ownerApprovedOn', 'sceneId', 'outlineId',
                  'templateSourceSha256', *_HASH_FIELDS}
        _require(set(row) == fields and _ID.fullmatch(row['page']) and _ID.fullmatch(row['outlineId'])
                 and row['sceneId'] == 'scene-' + row['outlineId'] and row['sceneId'] in by_id
                 and row['sceneId'] not in seen
                 and row['template'] in _SOURCE_TEMPLATES and type(row['version']) is int and row['version'] == 1
                 and isinstance(row['ownerApprovedOn'], str)
                 and date.fromisoformat(row['ownerApprovedOn']).isoformat() == row['ownerApprovedOn']
                 and all(_SHA.fullmatch(row[k]) for k in (*_HASH_FIELDS, 'templateSourceSha256')))
        seen.add(row['sceneId'])


def validate_release_controls(frozen, release):
    """Validate stored evidence without requiring the operator's build tree."""
    if FIELD not in frozen and FIELD not in release:
        return
    try:
        proof = frozen[FIELD]
        light = frozen['coursewareLight']
        base_fields = {'schemaVersion', 'brief', 'bodySha256', 'scenes'}
        _require(proof['bodySha256'] == light['source']['bodySha256'] == frozen['sourceSha256']
                 and digest(proof['brief']) == light['evidence']['briefSha256'])
        if proof['schemaVersion'] == SOURCE_PROOF_SCHEMA:
            _require(set(proof) == base_fields | {'sourceStageId', 'catalogSha256', 'mediaSha256'}
                     and _ID.fullmatch(proof['sourceStageId']) and proof['sourceStageId'] == light['source']['stageId']
                     and _SHA.fullmatch(proof['catalogSha256']) and proof['mediaSha256'] == _media_sha(
                         [{'sourceName': row['sourceName'], 'sha256': row['sha256']} for row in frozen['media']]))
            by_id = {s['id']: s for s in release['classroom']['scenes'] if s.get('type') == 'interactive'}
            _check_source_rows(proof['scenes'], by_id)
            _check_source_brief(proof['brief'], frozen['textbookBinding'], proof['scenes'],
                                {sid: scene['order'] for sid, scene in by_id.items()}, proof['catalogSha256'])
            _require(release[FIELD] == descriptors(proof, release['classroom']))
            return
        _require(set(proof) == base_fields and proof['schemaVersion'] == SCHEMA)
        declarations = _game_declarations(proof['brief'], frozen['textbookBinding'])
        rows = proof['scenes']
        _require(isinstance(rows, list) and len(rows) == len(declarations))
        seen = set()
        for row in rows:
            declared = declarations[row['page']]
            _require(set(row) == set(declared) | {'sceneId', 'outlineId', *_HASH_FIELDS} and row['page'] not in seen
                     and all(row[k] == v for k, v in declared.items())
                     and all(isinstance(row[key], str) and _SHA.fullmatch(row[key]) for key in _HASH_FIELDS))
            seen.add(row['page'])
        _require(release[FIELD] == descriptors(proof, release['classroom']))
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError('student_activity_controls_invalid') from exc
