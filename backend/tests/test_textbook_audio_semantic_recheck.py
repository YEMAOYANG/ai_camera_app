import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from content.textbook_catalog import digest
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError
from scripts.review_textbook_audio_mismatch import review, preflight
from services.textbook_batch_audio import save_json


class SemanticRecheckTests(unittest.TestCase):
    def test_paid_recognition_is_once_and_preserves_pending_review(self):
        class Runtime:
            base_url = 'http://127.0.0.1:3100'
            starts = 0

            def get_formal_audio_asr(self, request_id):
                raise OpenMaicFullRuntimeError('missing', 'missing', status_code=404)

            def start_formal_audio_asr(self, **payload):
                self.starts += 1
                text = 'a corrected transcript'
                return {'requestId':payload['request_id'], 'status':'succeeded',
                        'transcript':text, 'transcriptSha256':hashlib.sha256(text.encode()).hexdigest()}

        runtime = Runtime()
        with tempfile.TemporaryDirectory() as folder:
            evidence = {'requestId':'fixed-request', 'publicationAllowed':False,
                        'semanticReviewStatus':'pending', 'humanListeningVerified':False}
            payload = {'request_id':'fixed-request', 'tts_request_id':'original'}
            with patch('scripts.review_textbook_audio_mismatch.preflight',
                       return_value=(Path(folder),evidence,payload,runtime.base_url)):
                first = review(folder,'scene','segment',runtime)
                second = review(folder,'scene','segment',runtime)
            self.assertEqual(runtime.starts,1)
            self.assertEqual(first,second)
            self.assertFalse(first['publicationAllowed'])
            self.assertEqual(first['semanticReviewStatus'],'pending')

    def test_unknown_prior_dispatch_cannot_start_again(self):
        class Runtime:
            base_url = 'http://127.0.0.1:3100'

            def get_formal_audio_asr(self, request_id):
                raise OpenMaicFullRuntimeError('missing', 'missing', status_code=404)

            def start_formal_audio_asr(self, **payload):
                raise AssertionError('unknown requests must never be sent again')

        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            evidence = {'requestId':'fixed-request'}
            payload = {'request_id':'fixed-request'}
            save_json(output/'fixed-request.json',{'requestId':'fixed-request',
                      'requestPayloadSha256':digest(payload),'state':'dispatching'})
            with patch('scripts.review_textbook_audio_mismatch.preflight',
                       return_value=(output,evidence,payload,Runtime.base_url)):
                with self.assertRaisesRegex(RuntimeError,'unresolved_no_retry'):
                    review(folder,'scene','segment',Runtime())

    def test_changed_receipt_or_wrong_candidate_fails_before_configuration(self):
        with tempfile.TemporaryDirectory() as folder:
            # An absent or modified candidate cannot reach a paid operation.
            with self.assertRaises((ValueError, FileNotFoundError)):
                preflight(folder,'scene','segment')


if __name__ == '__main__':
    unittest.main()
