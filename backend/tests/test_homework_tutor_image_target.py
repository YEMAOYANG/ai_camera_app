"""Pure geometry tests: no database, model calls or real homework assets."""
from copy import deepcopy
import hashlib
import io
from unittest import TestCase

from PIL import Image, ImageDraw

from services.homework_tutor_image_target import (IMAGE_SCHEMA, attach_target_markers,
    region_from_target_input, region_to_target_input, target_contract_valid,
    target_observation_matches, verified_answer_target)


def fixture():
    photo = Image.new('RGB', (800, 1000), 'white')
    draw = ImageDraw.Draw(photo)
    draw.ellipse((120, 200, 190, 270), fill='red')
    draw.ellipse((220, 200, 290, 270), fill='green')
    draw.rectangle((100, 350, 660, 386), outline='black')
    draw.text((130, 355), '3 O [] = []', fill='black')
    draw.text((440, 355), '1', fill='blue')
    body = io.BytesIO(); photo.save(body, format='PNG'); image = body.getvalue()
    answer = {'x': .54, 'y': .354, 'width': .045, 'height': .025}
    result = {'method': 'tencent_question.v1', 'region': {'x': .125, 'y': .35, 'width': .7, 'height': .0367},
        'sourceAnswerOrdinal': 2, 'sourceAnswerCount': 3,
        'sourceValidation': {'geometryVerified': True, 'angleVerified': True},
        'providerAssessment': {'answerRegion': answer}}
    context = {'sourceDigest': 'a'*64, 'frameWidth': 800, 'frameHeight': 1000,
        'geometryVerified': False, 'region': None,
        'answerTarget': {'itemId': 'hwi_anonymous', 'index': 2, 'count': 3,
            'region': answer, 'geometryVerified': True}}
    contract = {'schemaVersion': 'mira.homework-tutor-image-input.v2', 'promptVersion': 'v8',
        'selection': 'full_page', 'modelCoordinateFrame': 'input_image', 'responseCoordinateFrame': 'original_page',
        'originalPageGeometry': {'width': 800, 'height': 1000},
        'inputGeometry': {'width': 800, 'height': 1000},
        'inputPixelBounds': {'left': 0, 'top': 0, 'right': 800, 'bottom': 1000},
        'inputWindow': {'x': 0, 'y': 0, 'width': 1, 'height': 1},
        'sourceImageSha256': hashlib.sha256(image).hexdigest(),
        'inputImageSha256': hashlib.sha256(image).hexdigest(),
        'contextGuard': {'geometryVerified': False, 'questionWindowSuitable': False,
            'sourceQuestionRegionInOriginalPage': result['region']}}
    return image, photo, result, context, contract


class VerifiedHomeworkAnswerTargetTests(TestCase):
    def target(self, result, context, page=None):
        return verified_answer_target(result, paper_context=context, page_geometry=page or {'width': 800, 'height': 1000})

    def test_exact_second_answer_survives_missing_shared_diagram_geometry(self):
        _, _, result, context, _ = fixture(); before = deepcopy((result, context))
        target = self.target(result, context)
        self.assertEqual(target['regionInOriginalPage'], result['providerAssessment']['answerRegion'])
        self.assertEqual((target['ordinal'], target['count']), (2, 3))
        self.assertEqual((result, context), before)

    def test_missing_mismatched_frame_angle_path_or_target_fails_closed(self):
        _, _, result, context, _ = fixture()
        cases = []
        bad = deepcopy(result); bad['providerAssessment']['geometryVerified'] = False; cases.append((bad, context))
        for angle in (False, None, 0, 'true'):
            bad = deepcopy(result); bad['sourceValidation']['angleVerified'] = angle; cases.append((bad, context))
        for change in ({'frameWidth': 801}, {'frameHeight': True}, {'sourceDigest': 'invalid'}, {'answerTarget': None}):
            cases.append((result, {**context, **change}))
        for change in ({'index': 1}, {'count': 4}, {'geometryVerified': False}, {'region': {'x': .6, 'y': .5, 'width': .04, 'height': .03}}):
            cases.append((result, {**context, 'answerTarget': {**context['answerTarget'], **change}}))
        for key, value in (('sourceAnswerOrdinal', True), ('sourceAnswerOrdinal', 0), ('sourceAnswerCount', 201)):
            cases.append(({**result, key: value}, context))
        for source, paper in cases:
            with self.subTest(source=source, paper=paper):
                self.assertIsNone(self.target(source, paper))
        self.assertIsNone(self.target(result, None))
        self.assertIsNone(self.target(result, context, {'width': True, 'height': 1000}))

    def test_same_ordinal_at_neighbouring_question_never_counts_as_current_target(self):
        _, _, result, context, _ = fixture()
        context.update(geometryVerified=True, region={'x': .125, 'y': .18, 'width': .7, 'height': .22})
        target = self.target(result, context)
        check = {'basis': 'original_image', 'questionLocated': True, 'questionReadable': True,
            'answerLocated': True, 'answerOrdinal': 2, 'questionRegion': result['region']}
        self.assertTrue(target_observation_matches(check, target))
        for update in ({'questionRegion': {'x': .1, 'y': .6, 'width': .7, 'height': .1}},
                {'questionRegion': {'x': 0, 'y': 0, 'width': 1, 'height': 1}},
                {'questionRegion': {'x': .125, 'y': .1, 'width': .7, 'height': .55}},
                {'answerOrdinal': 1}, {'answerOrdinal': True}, {'questionRegion': None}, {'answerLocated': False}):
            self.assertFalse(target_observation_matches({**check, **update}, target))
        self.assertFalse(target_observation_matches(check, None))
        context.update(geometryVerified=False, region=None)
        self.assertFalse(target_observation_matches(check, self.target(result, context)))
        # The observed region may include the actual shared diagram union.
        self.assertTrue(target_observation_matches({**check, 'questionRegion': target['questionRegionInOriginalPage']}, target))


class HomeworkExternalTargetMarkerTests(TestCase):
    target = VerifiedHomeworkAnswerTargetTests.target
    def marked(self):
        image, photo, result, context, base = fixture()
        target = self.target(result, context)
        marked, contract = attach_target_markers(image, base, target)
        return image, photo, result, base, marked, contract

    def test_full_page_narrow_row_keeps_every_original_pixel_and_diagram(self):
        image, photo, result, base, marked, contract = self.marked()
        self.assertEqual(contract['schemaVersion'], IMAGE_SCHEMA)
        self.assertEqual(contract['selection'], 'full_page')
        self.assertEqual(contract['inputWindow'], base['inputWindow'])
        self.assertFalse(contract['contextGuard']['questionWindowSuitable'])
        self.assertEqual(result['region']['height'], .0367)
        content = contract['sourceContentPixelBoundsInInput']
        rendered = Image.open(io.BytesIO(marked)).convert('RGB')
        original = rendered.crop(tuple(content[key] for key in ('left', 'top', 'right', 'bottom')))
        self.assertEqual(original.tobytes(), photo.tobytes())
        self.assertEqual(original.getpixel((155, 235)), (255, 0, 0))
        self.assertEqual(contract['sourceImageSha256'], hashlib.sha256(image).hexdigest())
        self.assertEqual(contract['inputImageSha256'], hashlib.sha256(marked).hexdigest())
        self.assertTrue(target_contract_valid(contract, base_image_bytes=image, input_image_bytes=marked))

    def test_missing_target_preserves_prior_v2_image_and_contract(self):
        image, _, _, _, base = fixture(); before = deepcopy(base)
        unchanged, contract = attach_target_markers(image, base, None)
        self.assertEqual(unchanged, image); self.assertEqual(contract, before)
        self.assertFalse(target_contract_valid(contract))

    def test_target_and_whole_page_regions_round_trip_with_margin_offset(self):
        _, _, result, _, _, contract = self.marked()
        for region in (result['region'], result['providerAssessment']['answerRegion'], {'x': 0, 'y': 0, 'width': 1, 'height': 1}):
            with self.subTest(region=region):
                local = region_to_target_input(region, contract)
                mapped = region_from_target_input(local, contract)
                for key in region:
                    self.assertAlmostEqual(mapped[key], region[key], places=5)
        self.assertEqual(contract['targetReference']['regionInInput'], region_to_target_input(result['providerAssessment']['answerRegion'], contract))

    def test_legal_complete_question_crop_maps_back_once_without_expanding_source_window(self):
        image, photo, result, context, base = fixture()
        box = (80, 180, 720, 420); cropped = photo.crop(box)
        body = io.BytesIO(); cropped.save(body, format='PNG'); crop_bytes = body.getvalue()
        base.update(selection='question_region', inputGeometry={'width': 640, 'height': 240},
            inputPixelBounds={'left': 80, 'top': 180, 'right': 720, 'bottom': 420},
            inputWindow={'x': .1, 'y': .18, 'width': .8, 'height': .24},
            inputImageSha256=hashlib.sha256(crop_bytes).hexdigest())
        marked, contract = attach_target_markers(crop_bytes, base, self.target(result, context))
        mapped = region_from_target_input(contract['targetReference']['regionInInput'], contract)
        for key in mapped:
            self.assertAlmostEqual(mapped[key], result['providerAssessment']['answerRegion'][key], places=5)
        self.assertEqual(contract['sourceImageSha256'], hashlib.sha256(image).hexdigest())
        self.assertTrue(target_contract_valid(contract, base_image_bytes=crop_bytes, input_image_bytes=marked))
        self.assertIsNone(region_to_target_input({'x': .1, 'y': .8, 'width': .1, 'height': .1}, contract))

    def test_margin_and_invalid_model_regions_are_rejected_without_relocating(self):
        _, _, _, _, _, contract = self.marked()
        for region in ({'x': 0, 'y': 0, 'width': .03, 'height': .03},
                {'x': 0, 'y': 0, 'width': 1, 'height': 1},
                {'x': True, 'y': .5, 'width': .1, 'height': .1},
                {'x': .5, 'y': .5, 'width': float('nan'), 'height': .1}):
            with self.subTest(region=region), self.assertRaises(ValueError):
                region_from_target_input(region, contract)
        content = contract['sourceContentPixelBoundsInInput']; size = contract['inputGeometry']
        edge_crossing = {'x': content['left']/size['width']-1e-7, 'y': .5, 'width': .05, 'height': .05}
        with self.assertRaises(ValueError):
            region_from_target_input(edge_crossing, contract)

    def test_tampered_target_frame_hash_and_content_fail_validation(self):
        image, _, _, _, marked, contract = self.marked()
        mutations = [lambda c: c['targetReference'].update(ordinal=True),
            lambda c: c['targetReference'].update(regionInInput={'x': .1, 'y': .1, 'width': .1, 'height': .1}),
            lambda c: c['sourceContentPixelBoundsInInput'].update(left=0),
            lambda c: c.update(inputImageSha256='b'*64),
            lambda c: c.update(sourceImageSha256='b'*64),
            lambda c: c.update(modelCoordinateFrame='original_page')]
        for mutate in mutations:
            changed = deepcopy(contract); mutate(changed)
            self.assertFalse(target_contract_valid(changed, base_image_bytes=image, input_image_bytes=marked))
        rendered = Image.open(io.BytesIO(marked)).convert('RGB')
        content = contract['sourceContentPixelBoundsInInput']
        rendered.putpixel((content['left']+155, content['top']+235), (0, 0, 0))
        body = io.BytesIO(); rendered.save(body, format='PNG'); tampered = body.getvalue()
        changed = deepcopy(contract); changed['inputImageSha256'] = hashlib.sha256(tampered).hexdigest()
        self.assertFalse(target_contract_valid(changed, base_image_bytes=image, input_image_bytes=tampered))

    def test_source_hash_or_dimensions_changed_before_marker_creation_fails(self):
        image, _, result, context, base = fixture(); target = self.target(result, context)
        changed = deepcopy(base); changed['inputImageSha256'] = 'b'*64
        with self.assertRaises(ValueError):
            attach_target_markers(image, changed, target)
        changed = deepcopy(base); changed['originalPageGeometry']['width'] = 801
        with self.assertRaises(ValueError):
            attach_target_markers(image, changed, target)
        with self.assertRaises(ValueError):
            attach_target_markers(image, base, {**target, 'ordinal': True})
