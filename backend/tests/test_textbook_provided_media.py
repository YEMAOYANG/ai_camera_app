"""Local immutable-byte and scope fences; synthetic containers are not codec QA."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from content import textbook_provided_media as media
from content.textbook_batch import build_plan
from content.textbook_batch_generation import freeze_input
from content.textbook_catalog import canonical, digest
from services.textbook_batch_generation_service import TextbookBatchGenerationService


def box(kind, payload=b''):
    return (len(payload)+8).to_bytes(4,'big')+kind+payload


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class ProvidedMediaTest(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);self.output=self.root/'output';self.output.mkdir()
        self.store=self.root/'store';self.store.mkdir()
        for name,value in (('ROOT',self.root),('OUTPUT_ROOT',self.output),('STORE_ROOT',self.store)):
            p=patch.object(media,name,value);p.start();self.addCleanup(p.stop)
        catalog=self.root/'catalog';catalog.mkdir()
        source=Path(__file__).parents[1]/'content/textbooks/official-directories-v1/bnu-math-g1-lower-2022-standard.directory-c4be26f1b4e105927cc4b5a0.json'
        (catalog/'book.json').write_text(source.read_text())
        _,tasks=build_plan(catalog,superseded_ids=set())
        self.task=next(t for t in tasks if t['kind']=='unit_guide')
        task_id=self.task['taskId'];binding=self.task['scope']
        self.raw=box(b'ftyp',b'isom'+b'\0'*4+b'isom')+box(b'moov')+box(b'mdat',b'fixture')
        video=self.output/'original.mp4';video.write_bytes(self.raw)
        renderer=self.output/'renderer.py';renderer.write_text('# synthetic scope fixture, not a codec\n')
        self.src=f'/api/classroom-media/tbmedia_{task_id[:12]}/media/counting-{sha(self.raw)[:16]}.mp4'
        self.installed=self.store/f'tbmedia_{task_id[:12]}'/'media'/self.src.rsplit('/',1)[1]
        self.installed.parent.mkdir(parents=True);self.installed.write_bytes(self.raw)
        receipt={'schemaVersion':'mira.textbook.provided-video-receipt.v1','taskId':task_id,
            'binding':binding,'assetId':'counting','sha256':sha(self.raw),'bytes':len(self.raw),'mimeType':'video/mp4',
            'src':self.src,'httpReadbackVerified':True,'rendererPath':str(renderer),
            'rendererSha256':sha(renderer.read_bytes()),'probe':{'codec':'h264','durationMs':12000,'width':960,'height':540}}
        self.receipt_path=self.output/'receipt.json';self.receipt_path.write_text(canonical(receipt))
        self.asset={'taskId':task_id,'binding':binding,'assetId':'counting','kind':'video','mimeType':'video/mp4',
            'originality':'original_programmatic_animation','sha256':sha(self.raw),'bytes':len(self.raw),
            'src':self.src,'localPath':str(video),'receiptPath':str(self.receipt_path),
            'receiptSha256':sha(self.receipt_path.read_bytes())}
        self.design={'schemaVersion':'mira.textbook.activity-design.v1','kind':'unit_guide',
            'status':'draft','publicationAllowed':False,'binding':binding,
            'manifestSha256':self.task['manifestSha256'],'designInstructions':'Watch original counting, then match pictures.',
            'providedMediaAssets':[self.asset]}
        self.design_path=self.output/'design.json';self.design_path.write_text(canonical(self.design))
        self.runtime=Mock(base_url='http://127.0.0.1:3100')
        self.runtime.start_generation.return_value=SimpleNamespace(job_id='job',status='queued')
        self.service=TextbookBatchGenerationService(self.root/'drafts',self.runtime)

    def freeze(self):
        return freeze_input(self.task,design_plan_path=self.design_path)

    def test_verified_original_video_disables_both_media_providers_but_stays_private(self):
        frozen=self.freeze()
        self.assertFalse(frozen['generationOptions']['enable_image_generation'])
        self.assertFalse(frozen['generationOptions']['enable_video_generation'])
        self.assertIn(self.src,frozen['requirement'])
        self.assertFalse(frozen['sourceReviewResolved'])
        self.assertFalse(frozen['publicationAllowed'])
        self.assertFalse(frozen['studentDeliveryAllowed'])
        self.service.prepare(frozen);self.service.start(frozen['taskId'])
        self.runtime.start_generation.assert_called_once()
        options=self.runtime.start_generation.call_args.kwargs
        self.assertFalse(options['enable_image_generation']);self.assertFalse(options['enable_video_generation'])

    def test_mutated_installed_video_stops_before_dispatch_without_claim_or_paid_call(self):
        frozen=self.freeze();self.service.prepare(frozen)
        self.installed.write_bytes(self.raw+b'changed')
        with self.assertRaisesRegex(ValueError,'file_hash_changed'):
            self.service.start(frozen['taskId'])
        self.assertEqual(self.service.get(frozen['taskId'])['status'],'prepared')
        self.assertFalse(self.service.get(frozen['taskId'])['providerDispatched'])
        self.runtime.start_generation.assert_not_called()

    def test_wrong_scope_foreign_url_and_missing_receipt_never_prepare(self):
        for change in ({'taskId':'b'*64},{'binding':{**self.task['scope'],'revisionId':'other'}},
                       {'src':'https://example.invalid/movie.mp4'},{'src':'/api/classroom-media/foreign/media/movie.mp4'},
                       {'receiptSha256':'f'*64}):
            design=deepcopy(self.design);design['providedMediaAssets'][0].update(change)
            self.design_path.write_text(canonical(design))
            with self.subTest(change=change),self.assertRaises(ValueError):self.freeze()
        self.runtime.start_generation.assert_not_called()

    def test_changed_renderer_receipt_or_original_source_rejects(self):
        for key in ('localPath','receiptPath'):
            path=Path(self.asset[key]);raw=path.read_bytes();path.write_bytes(raw+b'changed')
            with self.subTest(key=key),self.assertRaises(ValueError):self.freeze()
            path.write_bytes(raw)
        renderer=Path(json.loads(self.receipt_path.read_text())['rendererPath'])
        renderer.write_text('changed renderer')
        with self.assertRaisesRegex(ValueError,'file_hash_changed'):self.freeze()
        self.runtime.start_generation.assert_not_called()

    def test_source_symlink_cannot_escape_owned_output(self):
        foreign=self.root/'not-public.mp4';foreign.write_bytes(self.raw)
        link=self.output/'link.mp4';link.symlink_to(foreign)
        design=deepcopy(self.design);design['providedMediaAssets'][0]['localPath']=str(link)
        self.design_path.write_text(canonical(design))
        with self.assertRaisesRegex(ValueError,'file_outside_owned_store'):self.freeze()
        self.runtime.start_generation.assert_not_called()

    def test_no_provided_asset_preserves_normal_generation_options(self):
        normal=freeze_input(self.task)
        self.assertTrue(normal['generationOptions']['enable_image_generation'])
        self.assertTrue(normal['generationOptions']['enable_video_generation'])
        self.assertNotIn('providedMediaPolicy',normal)
        design=deepcopy(self.design);design['providedMediaAssets']=[]
        self.design_path.write_text(canonical(design))
        with self.assertRaisesRegex(ValueError,'asset_list_invalid'):self.freeze()


if __name__=='__main__':unittest.main()
