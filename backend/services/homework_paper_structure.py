"""Read-only, bounded original-paper structure from bound private receipts.

This is presentation/guidance metadata, never a regrade or a raw OCR endpoint.
All regions use the transformed page sent to Tencent; a missing frame proof
keeps the full page available instead of guessing a crop or a question link.
"""
from __future__ import annotations

import hashlib
import re
from core.errors import ApiError
from services.homework_assets import transformed_geometry, transformed_image
from services.homework_tencent_grading import (
    HomeworkTencentGrading, SCHEMA as JOB_SCHEMA, NORMALIZED_SCHEMA,
    digest, parsed,
)
from services.homework_tencent_normalizer import (
    NORMALIZER_VERSION, MAX_ITEMS_PER_PAGE, _angle_verified, _matching_source, _normalized_region,
    _polygon, _question_label, _region,
)

SCHEMA = 'mira.homework-paper-structure.v1'
PROJECTION_VERSION = 'mira.homework-paper-structure-projection.v1'
MAX_NODES = 1000
MAX_DEPTH = 16
MAX_ELEMENTS = 1000
MAX_TEXT_CHARACTERS = 128000


def _safe_text(value, limit=4000):
    if not isinstance(value, str):
        return ''
    # Figure.Text may contain a provider image address. Literal OCR text is
    # allowed, but no signed URLs, data URI, HTML or long encoded payloads.
    value = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', value).strip()
    if re.search(r'(?:https?://|data:|base64|<\s*(?:img|script|iframe)\b)', value, re.I):
        return ''
    if len(value) > 1024 and re.fullmatch(r'[A-Za-z0-9+/=]+', value):
        return ''
    return value[:limit]


def _issue(issues, code):
    if code not in issues:
        issues.append(code)


def _coords(value, width, height, verified):
    position = _polygon(value) if isinstance(value, dict) else value
    return _region(position, width, height, angle_verified=verified)


def _coverage(issues, *, unavailable=False):
    return {'status': 'unavailable' if unavailable else 'partial' if issues else 'ready',
        'issues': list(issues)}


def _source_frame(submit, width, height):
    info = submit.get('Response', {}).get('QuestionInfo')
    if isinstance(info, dict):
        info = [info]
    if not isinstance(info, list) or len(info) != 1 or not isinstance(info[0], dict):
        return None
    frame = info[0]
    if (not _angle_verified(frame.get('Angle'))
            or any(type(frame.get(k)) is not int or frame[k] != v for k, v in
                (('Width', width), ('OrgWidth', width), ('Height', height), ('OrgHeight', height)))):
        return None
    return frame


def _source_entries(frame, width, height, issues):
    """Keep QuestionInfo metadata independent of the MarkInfos tree.

    There is no official join key. A unique almost-identical question region
    is required before options/tables/figures can belong to a mark node.
    """
    candidates = []
    count = 0

    def visit(entries, depth=0):
        nonlocal count
        if not isinstance(entries, list):
            return
        if depth > MAX_DEPTH:
            _issue(issues, 'question_info_depth_limit')
            return
        for entry in entries:
            count += 1
            if count > MAX_ELEMENTS:
                _issue(issues, 'question_info_element_limit')
                return
            if not isinstance(entry, dict):
                _issue(issues, 'question_info_invalid')
                continue
            coords = entry.get('Coord')
            indexes = entry.get('CoordPageIndex') or []
            region = None
            if (isinstance(coords, list) and len(coords) == 1 and isinstance(indexes, list)
                    and indexes in ([], [1]) and all(type(index) is int for index in indexes)):
                region = _coords(coords[0], width, height, True)
            elements = entry.get('Question')
            elements = elements if isinstance(elements, list) else []
            prompt = '\n'.join(_safe_text(e.get('Text')) for e in elements
                if isinstance(e, dict) and type(e.get('PageIndex', 1)) is int and e.get('PageIndex', 1) == 1
                and _safe_text(e.get('Text')))
            page_ok = all(isinstance(e, dict) and type(e.get('PageIndex', 1)) is int
                and e.get('PageIndex', 1) == 1 for e in elements)
            if region and page_ok:
                candidates.append({'region': region, 'prompt': prompt, 'raw': entry})
            elif prompt or any(entry.get(kind) for kind in ('Figure', 'Option', 'Table')):
                _issue(issues, 'question_info_region_unverified')
            for kind in ('Question', 'Figure', 'Option', 'Table'):
                nested = entry.get(kind) or []
                if not isinstance(nested, list):
                    _issue(issues, 'question_info_invalid')
                    continue
                for element in nested:
                    if isinstance(element, dict):
                        visit(element.get('ResultList'), depth + 1)

    visit(frame.get('ResultList'))
    return candidates


def _elements(entry, kind, node_id, width, height, issues):
    values = entry.get(kind) or []
    if not isinstance(values, list):
        _issue(issues, 'question_info_invalid')
        return []
    result = []
    for index, element in enumerate(values[:MAX_ELEMENTS], 1):
        if not isinstance(element, dict):
            continue
        page_ok = type(element.get('PageIndex', 1)) is int and element.get('PageIndex', 1) == 1
        region = _coords(element.get('Coord'), width, height, page_ok)
        # Tencent Element uses CoordPolygon on some output shapes.
        if region is None:
            region = _coords(element.get('CoordPolygon'), width, height, page_ok)
        identity = 'hwpe_' + digest([node_id, kind, index])[:32]
        if kind == 'Figure':
            # Figure.Text describes an image address/position, not its caption.
            if region is None:
                _issue(issues, 'illustration_region_unverified')
            result.append({'id': identity, 'region': region, 'geometryVerified': region is not None})
        else:
            text = _safe_text(element.get('Text'))
            if not text and region is None:
                continue
            value = {'id': identity, 'text': text, 'region': region, 'geometryVerified': region is not None}
            if kind == 'Option':
                number = element.get('Index')
                value['label'] = str(number) if type(number) is int and 0 <= number <= 1000 else None
            if region is None:
                _issue(issues, 'option_region_unverified' if kind == 'Option' else 'table_region_unverified')
            result.append(value)
    if len(values) > MAX_ELEMENTS:
        _issue(issues, 'question_info_element_limit')
    return result


def _current_source(host, page):
    original = host.store.read(page['storage_key'])
    if hashlib.sha256(original).hexdigest() != page['content_sha256']:
        raise ValueError('source_asset_changed')
    transformed, image = transformed_image(original, page['rotation'], parsed(page['crop_json']))
    try:
        width, height = image.size
    finally:
        image.close()
    if (width, height) != transformed_geometry(page['width'], page['height'], page['rotation'], parsed(page['crop_json']))[0]:
        raise ValueError('source_geometry_changed')
    return digest({'image': hashlib.sha256(transformed).hexdigest(), 'analysisKind': 'questions',
        'provider': 'tencent', 'contract': JOB_SCHEMA}), width, height


def _call_proof(call, receipt, owner, page_id, source_sha, row, width, height):
    context = receipt.get('semanticContext')
    if (not isinstance(context, dict) or receipt.get('schemaVersion') != JOB_SCHEMA
            or receipt.get('analysisKind') != 'questions' or call['status'] == 'deleted'
            or call['provider'] != 'tencent' or call['submission_id'] != owner['id']
            or call['child_id'] != row['child_id'] or owner['child_id'] != row['child_id']
            or owner['family_id'] != row['family_id'] or owner['deleted_at'] is not None
            or call['page_id'] != page_id or receipt.get('analysisRevision') != owner['revision']
            or receipt.get('sourceSha256') != source_sha
            or context.get('gradeCode') != row['grade_code'] or context.get('subject') != row['subject']
            or context.get('normalizerVersion') != NORMALIZED_SCHEMA
            or context.get('providerConfigVersion') != 'tencent-ocr-2018-11-19.v1'
            or not isinstance(context.get('providerConfig'), dict)
            or not re.fullmatch(r'[a-f0-9]{64}', str(context.get('policySha256', '')))
            or type(receipt.get('width')) is not int or receipt['width'] != width
            or type(receipt.get('height')) is not int or receipt['height'] != height):
        return False
    request_sha = digest({'sourceSha256': source_sha, 'grade': row['grade_code'], 'subject': row['subject'],
        'policySha256': context['policySha256'], 'normalizerVersion': context['normalizerVersion'],
        'providerConfig': context['providerConfig'], 'providerConfigVersion': context['providerConfigVersion']})
    return call['request_sha256'] == request_sha and call['id'] == 'hwcall_' + digest([owner['id'], page_id, request_sha])[:56]


def _bound_receipts(host, conn, row, page):
    source_sha, width, height = _current_source(host, page)
    owned = conn.execute('SELECT * FROM homework_provider_calls WHERE submission_id=? AND page_id=? AND provider=?',
        (row['id'], page['id'], 'tencent')).fetchall()
    candidates = [(call, row) for call in owned]
    if not candidates:
        # Production may reuse the same child's live saved result, without a
        # new call. The original live owner/revision still binds the journals.
        reused = conn.execute('SELECT c.* FROM homework_provider_calls c JOIN homework_submissions s ON s.id=c.submission_id '
            'WHERE c.child_id=? AND s.family_id=? AND s.deleted_at IS NULL AND c.provider=? AND c.status=? '
            'AND c.receipt_json LIKE ?', (row['child_id'], row['family_id'], 'tencent', 'succeeded', '%' + source_sha + '%')).fetchall()
        for call in reused:
            owner = conn.execute('SELECT * FROM homework_submissions WHERE id=?', (call['submission_id'],)).fetchone()
            if owner:
                candidates.append((call, owner))
    matches = []
    for call, owner in candidates:
        receipt = parsed(call['receipt_json'], {})
        if isinstance(receipt, dict) and _call_proof(call, receipt, owner, call['page_id'], source_sha, row, width, height):
            matches.append((call, owner, receipt))
    if len(matches) != 1:
        raise ValueError('receipt_missing' if not matches else 'receipt_ambiguous')
    call, owner, receipt = matches[0]
    loader = HomeworkTencentGrading(host)
    job, bound_page = {'revision': owner['revision']}, {'id': call['page_id']}
    submit = receipt.get('submitResponse')
    expected_submit_key = host.store.response_key('homework-tencent:' + call['id'] + ':submit')
    if (not isinstance(submit, dict) or submit.get('attempt') != 'submit'
            or submit.get('storageKey') != expected_submit_key or receipt.get('requestJournalKey') != expected_submit_key):
        raise ValueError('receipt_digest_unavailable')
    submit_raw = loader._load_raw(job, owner, bound_page, call, expected_submit_key, reference=submit)
    response = submit_raw.get('Response') if isinstance(submit_raw, dict) else None
    if not isinstance(response, dict) or response.get('Error'):
        raise ValueError('submit_receipt_invalid')
    # Job ids must remain exactly those accepted by this submit, in their
    # original order; no association by a second independent array's order.
    ids = loader._job_ids({'jobId': response.get('JobId'), 'jobIds': response.get('JobIds')})
    if ids != receipt.get('jobIds'):
        raise ValueError('receipt_job_identity_changed')
    completed = receipt.get('completedJobs')
    if not isinstance(completed, dict) or any(key not in ids for key in completed):
        raise ValueError('receipt_job_identity_changed')
    raws, refs = [], [submit]
    for index, identity in enumerate(ids):
        reference = completed.get(identity)
        if (not isinstance(reference, dict) or not re.fullmatch(r'poll:' + str(index) + r':\d+', str(reference.get('attempt', '')))
                or reference.get('storageKey') != host.store.response_key('homework-tencent:' + call['id'] + ':' + reference['attempt'])):
            raise ValueError('completed_receipt_missing')
        # Do not use the legacy inline-body fallback: every structure result
        # must be read from the exact digest-checked private poll envelope.
        raw = loader._load_raw(job, owner, bound_page, call, reference['storageKey'],
            attempt=reference['attempt'], reference=reference)
        poll_response = raw.get('Response') if isinstance(raw, dict) else None
        if (not isinstance(poll_response, dict) or poll_response.get('Error')
                or poll_response.get('JobStatus') != 'DONE'):
            raise ValueError('completed_receipt_missing')
        raws.append(raw)
        refs.append(reference)
    geometry = receipt.get('submittedGeometry')
    geometry = geometry if isinstance(geometry, dict) else {}
    frame = _source_frame(submit_raw, width, height)
    # Current adapters submit the same size. Legacy missing geometry can be
    # corroborated by QuestionInfo's four exact dimensions and zero angle.
    geometry_ok = all(geometry.get(key) in (None, dimension) for key, dimension in
        (('inputWidth', width), ('submittedWidth', width), ('inputHeight', height), ('submittedHeight', height)))
    proof_digest = digest({'sourceSha256': source_sha, 'requestSha256': call['request_sha256'],
        'ownerRevision': owner['revision'], 'submitAndResults': [{k: ref.get(k) for k in ('sha256', 'rawSha256', 'attempt')} for ref in refs],
        'submittedGeometry': geometry, 'pageContentSha256': page['content_sha256'],
        'rotation': page['rotation'], 'crop': parsed(page['crop_json'])})
    return raws, submit_raw, frame if geometry_ok else None, width, height, proof_digest


def _item_link(row, page, items_by_order, order, mark, answer, ancestors, receipt_index, path, answer_index, count):
    # This is the *same* DFS producer that originally persisted hwi ids, not a
    # spatial/array-order join between QuestionInfo and MarkInfos. Check the
    # immutable id and actual saved AnswerInfo too, including old v2 rows.
    expected = 'hwi_' + digest([row['id'], row['revision'], page['id'], page['content_sha256'],
        page['rotation'], parsed(page['crop_json']), order])[:56]
    item = items_by_order.get(order)
    if (not item or item['id'] != expected or item['page_id'] != page['id']
            or item['analysis_revision'] != row['revision']):
        return None
    result = parsed(item['result_json'], {})
    raw = result.get('tencentRaw') if isinstance(result, dict) else None
    if (result.get('method') != 'tencent_question.v1' or not isinstance(raw, dict)
            or not isinstance(raw.get('mark'), dict) or raw['mark'].get('MarkItemTitle', '') != mark.get('MarkItemTitle', '')
            or result.get('ancestorContext', []) != list(ancestors)
            or raw.get('answer') != answer):
        return None
    hierarchy = result.get('sourceHierarchy')
    if isinstance(hierarchy, dict) and hierarchy.get('hierarchyVerified') is True:
        if (hierarchy.get('receiptIndex') != receipt_index or hierarchy.get('markPath') != list(path)
                or hierarchy.get('answerIndex') != answer_index or hierarchy.get('answerCount') != count):
            return None
    elif answer is not None and (result.get('sourceAnswerOrdinal') != answer_index or result.get('sourceAnswerCount') != count):
        return None
    return item['id']


def _project_page(row, page, page_items, raws, frame, width, height, proof_digest):
    issues, linked, questions = [], set(), []
    candidates = _source_entries(frame, width, height, issues) if frame else []
    if frame is None:
        _issue(issues, 'coordinate_frame_unverified')
    order, node_count, element_count, text_count = 0, 0, 0, 0
    matched_source_ids = set()
    by_order = {}
    for item in page_items:
        key = item['item_order']
        by_order[key] = item if key not in by_order else None
    page_geometry = bool(frame) and all(_angle_verified(raw.get('Response', {}).get('Angle')) for raw in raws)

    def walk(mark, angle, receipt_index, path, ancestors=(), depth=0):
        nonlocal order, node_count, element_count, text_count
        node_count += 1
        if depth > MAX_DEPTH or node_count > MAX_NODES:
            _issue(issues, 'question_tree_limit')
            return None
        if not isinstance(mark, dict):
            _issue(issues, 'question_tree_invalid')
            return None
        title = _safe_text(mark.get('MarkItemTitle'))
        verified = frame is not None and _angle_verified(angle)
        region = _coords(mark.get('QuestionPositions'), width, height, verified)
        match = _matching_source(candidates, region)
        if match:
            matched_source_ids.add(id(match))
        identity = 'hwq_' + digest([row['id'], row['revision'], page['id'], proof_digest, receipt_index, path])[:32]
        prompt = match['prompt'] if match and match['prompt'] else title
        remaining_text = max(0, MAX_TEXT_CHARACTERS - text_count)
        if len(prompt) > remaining_text:
            prompt = prompt[:remaining_text]
            _issue(issues, 'question_text_limit')
        text_count += len(prompt)
        node = {'id': identity, 'label': _question_label(title), 'prompt': prompt, 'region': region,
            'geometryVerified': region is not None, 'illustrations': [], 'options': [], 'tables': [], 'answers': [], 'children': []}
        if prompt and region is None:
            _issue(issues, 'question_region_unverified')
        if not prompt:
            _issue(issues, 'question_text_missing')
        images = mark.get('QuestionImagePositions') or []
        if isinstance(images, list):
            for index, image in enumerate(images[:max(0, MAX_ELEMENTS-element_count)], 1):
                element_count += 1
                image_region = _coords(image.get('Position'), width, height, verified) if isinstance(image, dict) else None
                node['illustrations'].append({'id': 'hwpe_' + digest([identity, 'mark_image', index])[:32],
                    'region': image_region, 'geometryVerified': image_region is not None})
                if image_region is None:
                    _issue(issues, 'illustration_region_unverified')
            if len(images) > max(0, MAX_ELEMENTS-element_count) + len(node['illustrations']):
                _issue(issues, 'question_info_element_limit')
        else:
            _issue(issues, 'illustration_structure_invalid')
        if match:
            for kind, key in (('Figure', 'illustrations'), ('Option', 'options'), ('Table', 'tables')):
                values = _elements(match['raw'], kind, identity, width, height, issues)
                available = max(0, MAX_ELEMENTS - element_count)
                if len(values) > available:
                    _issue(issues, 'question_info_element_limit')
                values = values[:available]
                for value in values:
                    if 'text' in value:
                        remaining_text = max(0, MAX_TEXT_CHARACTERS - text_count)
                        if len(value['text']) > remaining_text:
                            _issue(issues, 'question_text_limit')
                        value['text'] = value['text'][:remaining_text]
                        text_count += len(value['text'])
                element_count += len(values)
                node[key].extend(values)
        answers, children = mark.get('AnswerInfos') or [], mark.get('MarkInfos') or []
        if not isinstance(answers, list) or not isinstance(children, list):
            _issue(issues, 'question_tree_invalid')
            return node
        available_targets = max(0, MAX_ITEMS_PER_PAGE-order)
        target_count = len(answers) if answers else int(not children)
        if target_count > available_targets:
            _issue(issues, 'answer_item_limit')
        targets = list(enumerate(answers[:available_targets], 1)) if answers else [(None, None)] if not children and available_targets else []
        for answer_index, answer in targets:
            linked_id = _item_link(row, page, by_order, order, mark, answer, ancestors,
                receipt_index, path, answer_index, len(answers))
            order += 1
            answer_region = _coords(answer.get('HandwriteInfoPositions'), width, height, verified) if isinstance(answer, dict) else None
            if linked_id:
                linked.add(linked_id)
                node['answers'].append({'itemId': linked_id, 'index': answer_index, 'count': len(answers),
                    'region': answer_region, 'geometryVerified': answer_region is not None})
                if answer is not None and answer_region is None:
                    _issue(issues, 'answer_region_unverified')
            else:
                _issue(issues, 'answer_item_link_unverified')
        for index, child in enumerate(children, 1):
            value = walk(child, angle, receipt_index, (*path, index),
                (*ancestors, title) if title else ancestors, depth + 1)
            if value:
                node['children'].append(value)
        return node

    for receipt_index, raw in enumerate(raws, 1):
        response = raw['Response']
        marks = response.get('MarkInfos')
        if not isinstance(marks, list):
            _issue(issues, 'question_tree_invalid')
            continue
        for index, mark in enumerate(marks, 1):
            value = walk(mark, response.get('Angle'), receipt_index, (index,))
            if value:
                questions.append(value)
    unassigned = [item['id'] for item in page_items if item['id'] not in linked]
    if unassigned:
        _issue(issues, 'answer_item_link_unverified')
    if any(id(candidate) not in matched_source_ids and
            (candidate['prompt'] or any(candidate['raw'].get(kind) for kind in ('Figure', 'Option', 'Table')))
            for candidate in candidates):
        _issue(issues, 'question_info_owner_unverified')
    return {'pageId': page['id'], 'frameWidth': width, 'frameHeight': height,
        'geometryVerified': page_geometry, 'coverage': _coverage(issues, unavailable=not questions),
        'questions': questions, 'unassignedItemIds': unassigned}, len(linked)


def paper_structure(host, conn, row, *, pages=None, items=None):
    """Details only. Reads private saved data; never calls a provider or writes."""
    fresh = conn.execute('SELECT * FROM homework_submissions WHERE id=?', (row['id'],)).fetchone()
    if (not fresh or fresh['deleted_at'] is not None or any(fresh[key] != row[key]
            for key in ('family_id', 'child_id', 'revision', 'subject', 'grade_code'))):
        return None
    pages = host.repository.pages(conn, row['id']) if pages is None else pages
    items = host.repository.items(conn, row['id']) if items is None else items
    tencent_items = [item for item in items if parsed(item['result_json'], {}).get('method') == 'tencent_question.v1']
    if not tencent_items:
        return None
    projected, proofs, issues, linked = [], [], [], 0
    for page in pages:
        page_items = [item for item in tencent_items if item['page_id'] == page['id']]
        if not page_items:
            continue
        try:
            raws, submit, frame, width, height, proof = _bound_receipts(host, conn, row, page)
            view, count = _project_page(row, page, page_items, raws, frame, width, height, proof)
            linked += count
            proofs.append(proof)
        except (ApiError, OSError, ValueError, TypeError, KeyError, IndexError, RecursionError) as error:
            # Deliberately no private exception/raw data in the DTO or logs.
            reason = str(error) if type(error) is ValueError and str(error) in {
                'source_asset_changed', 'source_geometry_changed', 'receipt_missing', 'receipt_ambiguous', 'receipt_digest_unavailable',
                'receipt_job_identity_changed', 'completed_receipt_missing', 'submit_receipt_invalid'} else 'receipt_unavailable'
            width, height = transformed_geometry(page['width'], page['height'], page['rotation'], parsed(page['crop_json']))[0]
            view = {'pageId': page['id'], 'frameWidth': width, 'frameHeight': height, 'geometryVerified': False,
                'coverage': _coverage([reason], unavailable=True), 'questions': [],
                'unassignedItemIds': [item['id'] for item in page_items]}
            proofs.append(digest({'pageId': page['id'], 'contentSha256': page['content_sha256'],
                'rotation': page['rotation'], 'crop': parsed(page['crop_json']), 'reason': reason}))
        projected.append(view)
        for issue in view['coverage']['issues']:
            _issue(issues, issue)
    source_digest = digest({'projectionVersion': PROJECTION_VERSION, 'normalizerVersion': NORMALIZER_VERSION,
        'submissionId': row['id'], 'analysisRevision': row['revision'], 'pages': proofs,
        'items': [{'id': item['id'], 'revision': item['revision'], 'analysisRevision': item['analysis_revision'],
            'resultSha256': digest(parsed(item['result_json'], {}))} for item in tencent_items]})
    coverage = _coverage(issues, unavailable=not any(page['questions'] for page in projected))
    coverage.update(linkedAnswers=linked, totalAnswers=len(tencent_items))
    return {'schemaVersion': SCHEMA, 'projectionVersion': PROJECTION_VERSION, 'sourceDigest': source_digest,
        'coverage': coverage, 'pages': projected}


def selected_item_context(host, conn, row, item):
    """A safe exact-item path for the teacher, in the original page frame.

    Root can bind sourceDigest to its provider request and map ``region`` to a
    teaching crop. Missing shared text/diagram coordinates means full-page
    guidance; this function provides no grading authority.
    """
    structure = paper_structure(host, conn, row)
    if not structure:
        return None
    if item['submission_id'] != row['id'] or item['analysis_revision'] != row['revision']:
        return None

    def find(nodes, path=()):
        for node in nodes:
            chain = (*path, node)
            answer = next((value for value in node['answers'] if value['itemId'] == item['id']), None)
            if answer:
                return chain, answer
            found = find(node['children'], chain)
            if found:
                return found
        return None

    page = next((page for page in structure['pages'] if page['pageId'] == item['page_id']), None)
    found = find(page['questions']) if page else None
    if not found:
        return {'schemaVersion': SCHEMA, 'sourceDigest': structure['sourceDigest'], 'pageId': item['page_id'],
            'questionPath': [], 'sharedPrompts': [], 'region': None, 'geometryVerified': False,
            'illustrations': [], 'options': [], 'tables': [], 'answerTarget': None,
            'coverage': structure['coverage'], 'scope': 'original_paper_guidance_only'}
    path, answer = found
    pictures = [element for node in path for element in node['illustrations']]
    tables = [element for node in path for element in node['tables']]
    options = next((node['options'] for node in reversed(path) if node['options']), [])
    required = [node['region'] for node in path if node['prompt']] + [element['region'] for element in [*pictures, *tables, *options]]
    if answer['region']:
        required.append(answer['region'])
    verified = page['geometryVerified'] and bool(required) and all(_normalized_region(region) is not None for region in required)
    region = None
    if verified:
        left, top = min(value['x'] for value in required), min(value['y'] for value in required)
        right, bottom = max(value['x'] + value['width'] for value in required), max(value['y'] + value['height'] for value in required)
        region = {'x': left, 'y': top, 'width': right-left, 'height': bottom-top}
    return {'schemaVersion': SCHEMA, 'sourceDigest': structure['sourceDigest'], 'pageId': item['page_id'],
        'frameWidth': page['frameWidth'], 'frameHeight': page['frameHeight'],
        'questionPath': [{'id': node['id'], 'label': node['label'], 'prompt': node['prompt'],
            'region': node['region'], 'geometryVerified': node['geometryVerified']} for node in path],
        'sharedPrompts': [node['prompt'] for node in path if node['prompt']], 'region': region,
        'geometryVerified': bool(verified), 'illustrations': pictures, 'options': options, 'tables': tables,
        'answerTarget': answer, 'coverage': page['coverage'], 'scope': 'original_paper_guidance_only'}
