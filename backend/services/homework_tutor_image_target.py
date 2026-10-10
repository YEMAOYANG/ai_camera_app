"""Exact answer targets and non-destructive teacher-image navigation cues.

This module only derives geometry from saved evidence. It neither reads a
database nor calls a model, and its arrows never draw on original paper pixels.
Target containment is a location prerequisite, not proof of an answer or stem.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import io
import math
import re

from PIL import Image, ImageDraw

from core.errors import ApiError
from services.homework_assets import crop_region
from services.homework_tencent_normalizer import grading_reference


IMAGE_SCHEMA = 'mira.homework-tutor-image-input.v3'
TARGET_SCHEMA = 'mira.homework-tutor-image-target.v1'
BASE_IMAGE_SCHEMA = 'mira.homework-tutor-image-input.v2'
MARKER_STYLE = 'margin_axis_arrows'
MARKER_COLOR = (18, 106, 124)


def _region(value):
    try:
        return crop_region(value)
    except (ApiError, ValueError, TypeError):
        return None


def _raw_region(value):
    # Service-generated frame fractions must not be rounded before the inverse
    # transform. Rounding an exact content edge could move it into a margin.
    return {key: float(number) for key, number in value.items()} if _region(value) is not None else None


def _contains(outer, inner):
    return bool(outer and inner and inner['x'] >= outer['x'] - 1e-6
        and inner['y'] >= outer['y'] - 1e-6
        and inner['x'] + inner['width'] <= outer['x'] + outer['width'] + 1e-6
        and inner['y'] + inner['height'] <= outer['y'] + outer['height'] + 1e-6)


def _geometry(value):
    if not isinstance(value, dict):
        return None
    width, height = value.get('width'), value.get('height')
    if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
        return None
    return {'width': width, 'height': height}


def _digest(value):
    return isinstance(value, str) and re.fullmatch(r'[a-f0-9]{64}', value) is not None


def verified_answer_target(result, *, page_geometry, paper_context=None):
    """Bind one Tencent answer to its exact saved item path and current frame.

    A shared diagram may lack coordinates while the answer's exact-item receipt
    remains valid. Its missing geometry still keeps the whole original page;
    it must not invalidate or fabricate a separately verified answer position.
    """
    page = _geometry(page_geometry)
    if page is None or not isinstance(result, dict) or result.get('method') != 'tencent_question.v1':
        return None
    validation = result.get('sourceValidation')
    if not isinstance(validation, dict) or validation.get('angleVerified') is not True or validation.get('geometryVerified') is not True:
        return None
    ordinal, count = result.get('sourceAnswerOrdinal'), result.get('sourceAnswerCount')
    if type(ordinal) is not int or type(count) is not int or not 1 <= ordinal <= count <= 200:
        return None
    reference = grading_reference(result) or {}
    assessment = result.get('providerAssessment')
    if isinstance(assessment, dict) and assessment.get('geometryVerified') is False:
        return None
    question, answer = _region(result.get('region')), _region(reference.get('answerRegion'))
    if reference.get('geometryVerified') is not True or not _contains(question, answer) or question == answer:
        return None
    if not isinstance(paper_context, dict) or not _digest(paper_context.get('sourceDigest')):
        return None
    if (type(paper_context.get('frameWidth')) is not int or type(paper_context.get('frameHeight')) is not int
            or paper_context['frameWidth'] != page['width'] or paper_context['frameHeight'] != page['height']):
        return None
    exact = paper_context.get('answerTarget')
    if (not isinstance(exact, dict) or exact.get('geometryVerified') is not True
            or not isinstance(exact.get('itemId'), str) or not exact['itemId']
            or type(exact.get('index')) is not int or exact['index'] != ordinal
            or type(exact.get('count')) is not int or exact['count'] != count
            or _region(exact.get('region')) != answer):
        return None
    context_region = _region(paper_context.get('region'))
    context_verified = bool(paper_context.get('geometryVerified') is True
        and _contains(context_region, question) and _contains(context_region, answer))
    return {'schemaVersion': TARGET_SCHEMA, 'geometryVerified': True,
        'ordinal': ordinal, 'count': count, 'itemId': exact['itemId'],
        'sourceDigest': paper_context['sourceDigest'], 'originalPageGeometry': page,
        'regionInOriginalPage': answer, 'sourceQuestionRegionInOriginalPage': question,
        'questionRegionInOriginalPage': context_region if context_verified else None,
        'questionContextVerified': context_verified}


def _target_valid(target):
    if not isinstance(target, dict) or target.get('schemaVersion') != TARGET_SCHEMA or target.get('geometryVerified') is not True:
        return False
    ordinal, count = target.get('ordinal'), target.get('count')
    source_question = _region(target.get('sourceQuestionRegionInOriginalPage'))
    context = _region(target.get('questionRegionInOriginalPage'))
    context_verified = target.get('questionContextVerified')
    return bool(type(ordinal) is int and type(count) is int and 1 <= ordinal <= count <= 200
        and isinstance(target.get('itemId'), str) and target['itemId']
        and _digest(target.get('sourceDigest')) and _geometry(target.get('originalPageGeometry'))
        and _contains(source_question, _region(target.get('regionInOriginalPage')))
        and source_question != _region(target.get('regionInOriginalPage'))
        and type(context_verified) is bool
        and (context_verified and _contains(context, source_question)
            or not context_verified and target.get('questionRegionInOriginalPage') is None))


def _frame(contract):
    if not isinstance(contract, dict) or contract.get('schemaVersion') not in {BASE_IMAGE_SCHEMA, IMAGE_SCHEMA}:
        raise ValueError('invalid target image frame')
    page, size = _geometry(contract.get('originalPageGeometry')), _geometry(contract.get('inputGeometry'))
    bounds = contract.get('inputPixelBounds')
    if (page is None or size is None or not isinstance(bounds, dict)
            or any(type(bounds.get(key)) is not int for key in ('left', 'top', 'right', 'bottom'))):
        raise ValueError('invalid target image frame')
    left, top, right, bottom = (bounds[key] for key in ('left', 'top', 'right', 'bottom'))
    if not 0 <= left < right <= page['width'] or not 0 <= top < bottom <= page['height']:
        raise ValueError('invalid target source window')
    window = {'x': left/page['width'], 'y': top/page['height'],
        'width': (right-left)/page['width'], 'height': (bottom-top)/page['height']}
    if contract.get('inputWindow') != window:
        raise ValueError('invalid target source window')
    if contract.get('modelCoordinateFrame') != 'input_image' or contract.get('responseCoordinateFrame') != 'original_page':
        raise ValueError('invalid target coordinate frame')
    if contract.get('selection') == 'full_page':
        if (left, top, right, bottom) != (0, 0, page['width'], page['height']):
            raise ValueError('invalid target full page')
    elif contract.get('selection') != 'question_region':
        raise ValueError('invalid target selection')
    if contract['schemaVersion'] == BASE_IMAGE_SCHEMA:
        content = {'left': 0, 'top': 0, 'right': right-left, 'bottom': bottom-top}
    else:
        content = contract.get('sourceContentPixelBoundsInInput')
    if (not isinstance(content, dict) or any(type(content.get(key)) is not int for key in ('left', 'top', 'right', 'bottom'))
            or not 0 <= content['left'] < content['right'] <= size['width']
            or not 0 <= content['top'] < content['bottom'] <= size['height']
            or content['right']-content['left'] != right-left or content['bottom']-content['top'] != bottom-top):
        raise ValueError('invalid target content frame')
    if contract['schemaVersion'] == BASE_IMAGE_SCHEMA and size != {'width': right-left, 'height': bottom-top}:
        raise ValueError('invalid base image size')
    return page, bounds, size, content, window


def region_to_target_input(region, contract):
    """Map a source rectangle into the image, including its added margins."""
    page, bounds, size, content, window = _frame(contract)
    region = _region(region)
    if not _contains(window, region):
        return None
    return _raw_region({'x': (region['x']*page['width']-bounds['left']+content['left'])/size['width'],
        'y': (region['y']*page['height']-bounds['top']+content['top'])/size['height'],
        'width': region['width']*page['width']/size['width'],
        'height': region['height']*page['height']/size['height']})


def region_from_target_input(region, contract):
    """Reject any model rectangle outside the preserved source-content frame."""
    page, bounds, size, content, _ = _frame(contract)
    region = _raw_region(region)
    if region is None:
        raise ValueError('model region outside original paper content')
    left, top = region['x']*size['width'], region['y']*size['height']
    right, bottom = (region['x']+region['width'])*size['width'], (region['y']+region['height'])*size['height']
    # Only machine floating-point multiplication error is tolerated. A model's
    # actual margin rectangle is rejected; nothing is clipped or shifted.
    if (left < content['left']-1e-9 or top < content['top']-1e-9
            or right > content['right']+1e-9 or bottom > content['bottom']+1e-9):
        raise ValueError('model region outside original paper content')
    mapped = _region({'x': (bounds['left']+left-content['left'])/page['width'],
        'y': (bounds['top']+top-content['top'])/page['height'],
        'width': (right-left)/page['width'], 'height': (bottom-top)/page['height']})
    if mapped is None:
        raise ValueError('invalid mapped paper region')
    return mapped


def _draw_marker_arrows(output, target, content):
    region = target['regionInInput']
    margin = content['left']
    cx = round((region['x']+region['width']/2)*output.width)
    cy = round((region['y']+region['height']/2)*output.height)
    half, length, gap = max(6, margin//7), max(14, margin//2), 3
    draw = ImageDraw.Draw(output)
    draw.polygon([(cx, margin-gap), (cx-half, margin-gap-length), (cx+half, margin-gap-length)], fill=MARKER_COLOR)
    draw.polygon([(cx, content['bottom']+gap), (cx-half, content['bottom']+gap+length), (cx+half, content['bottom']+gap+length)], fill=MARKER_COLOR)
    draw.polygon([(margin-gap, cy), (margin-gap-length, cy-half), (margin-gap-length, cy+half)], fill=MARKER_COLOR)
    draw.polygon([(content['right']+gap, cy), (content['right']+gap+length, cy-half), (content['right']+gap+length, cy+half)], fill=MARKER_COLOR)


def attach_target_markers(image_bytes, image_contract, target_reference):
    """Add only external arrows; no target means exactly the prior v2 input."""
    if target_reference is None:
        return image_bytes, deepcopy(image_contract)
    if image_contract.get('schemaVersion') != BASE_IMAGE_SCHEMA or not _target_valid(target_reference):
        raise ValueError('invalid verified answer target')
    page, _, size, _, window = _frame(image_contract)
    if (page != target_reference['originalPageGeometry'] or not _contains(window, target_reference['regionInOriginalPage'])
            or not _digest(image_contract.get('sourceImageSha256'))
            or hashlib.sha256(image_bytes).hexdigest() != image_contract.get('inputImageSha256')):
        raise ValueError('target image source changed')
    with Image.open(io.BytesIO(image_bytes)) as decoded:
        decoded.load()
        source = decoded.convert('RGB')
    if source.size != (size['width'], size['height']):
        raise ValueError('target image dimensions changed')
    margin = max(32, min(128, math.ceil(max(source.size)*0.04)))
    output = Image.new('RGB', (source.width+2*margin, source.height+2*margin), 'white')
    output.paste(source, (margin, margin))
    contract = deepcopy(image_contract)
    content = {'left': margin, 'top': margin, 'right': margin+source.width, 'bottom': margin+source.height}
    contract.update(schemaVersion=IMAGE_SCHEMA,
        inputGeometry={'width': output.width, 'height': output.height},
        sourceContentPixelBoundsInInput=content,
        baseInputImageSha256=image_contract['inputImageSha256'])
    target = deepcopy(target_reference)
    target.update(coordinateFrame='input_image', markerStyle=MARKER_STYLE,
        semanticRole='answer_position_only', printedContent=False,
        sourceContentPixelBoundsInInput=deepcopy(content),
        regionInInput=region_to_target_input(target['regionInOriginalPage'], contract))
    contract['targetReference'] = target
    _draw_marker_arrows(output, target, content)
    body = io.BytesIO()
    output.save(body, format='PNG')
    image = body.getvalue()
    contract['inputImageSha256'] = hashlib.sha256(image).hexdigest()
    if not target_contract_valid(contract, base_image_bytes=image_bytes, input_image_bytes=image):
        raise ValueError('invalid generated target image')
    return image, contract


def target_contract_valid(contract, *, base_image_bytes=None, input_image_bytes=None):
    """Validate binding, frame and optional image hashes/pixel preservation."""
    try:
        if not isinstance(contract, dict) or contract.get('schemaVersion') != IMAGE_SCHEMA:
            return False
        page, _, size, content, _ = _frame(contract)
        target = contract.get('targetReference')
        mapped_target = region_to_target_input(target.get('regionInOriginalPage'), contract) if isinstance(target, dict) else None
        if (not _target_valid(target) or target['originalPageGeometry'] != page
                or target.get('coordinateFrame') != 'input_image'
                or target.get('markerStyle') != MARKER_STYLE or target.get('semanticRole') != 'answer_position_only'
                or target.get('printedContent') is not False
                or target.get('sourceContentPixelBoundsInInput') != content
                or mapped_target is None or target.get('regionInInput') != mapped_target
                or any(not _digest(contract.get(key)) for key in ('sourceImageSha256', 'baseInputImageSha256', 'inputImageSha256'))):
            return False
        if content['left'] < 32 or content['top'] != content['left'] or size['width']-content['right'] != content['left'] or size['height']-content['bottom'] != content['top']:
            return False
        source = rendered = None
        if base_image_bytes is not None:
            if hashlib.sha256(base_image_bytes).hexdigest() != contract['baseInputImageSha256']:
                return False
            with Image.open(io.BytesIO(base_image_bytes)) as decoded:
                decoded.load()
                source = decoded.convert('RGB')
            if source.size != (content['right']-content['left'], content['bottom']-content['top']):
                return False
            if contract['selection'] == 'full_page' and contract['sourceImageSha256'] != contract['baseInputImageSha256']:
                return False
        if input_image_bytes is not None:
            if hashlib.sha256(input_image_bytes).hexdigest() != contract['inputImageSha256']:
                return False
            with Image.open(io.BytesIO(input_image_bytes)) as decoded:
                decoded.load()
                rendered = decoded.convert('RGB')
            if rendered.size != (size['width'], size['height']):
                return False
            expected = Image.new('RGB', rendered.size, 'white')
            preserved = rendered.crop(tuple(content[key] for key in ('left', 'top', 'right', 'bottom')))
            expected.paste(preserved, (content['left'], content['top']))
            _draw_marker_arrows(expected, target, content)
            if rendered.tobytes() != expected.tobytes():
                return False
        return source is None or rendered is None or rendered.crop(tuple(content[key] for key in ('left', 'top', 'right', 'bottom'))).tobytes() == source.tobytes()
    except (ValueError, TypeError, KeyError, AttributeError, OSError):
        return False


def target_observation_matches(check, target_reference):
    """Same ordinal cannot turn a neighbouring question into this target."""
    if not _target_valid(target_reference) or not isinstance(check, dict):
        return False
    context = _region(target_reference.get('questionRegionInOriginalPage'))
    observed = _region(check.get('questionRegion'))
    if target_reference.get('questionContextVerified') is not True or context is None or observed is None:
        return False
    # A page-sized assertion carries no exact-question evidence, even when it
    # happens to contain the answer. Source context itself must be bounded too.
    if context['width']*context['height'] >= .9 or observed['width']*observed['height'] >= .9:
        return False
    page = target_reference['originalPageGeometry']
    padx, pady = 16/page['width'], 16/page['height']
    left, top = max(0, context['x']-padx), max(0, context['y']-pady)
    right = min(1, context['x']+context['width']+padx)
    bottom = min(1, context['y']+context['height']+pady)
    padded_context = {'x': left, 'y': top, 'width': right-left, 'height': bottom-top}
    return bool(check.get('basis') == 'original_image'
        and check.get('questionLocated') is True and check.get('questionReadable') is True
        and check.get('answerLocated') is True
        and type(check.get('answerOrdinal')) is int and check['answerOrdinal'] == target_reference['ordinal']
        and _contains(observed, target_reference['regionInOriginalPage'])
        and _contains(padded_context, observed))
