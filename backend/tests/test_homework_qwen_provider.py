"""Paper-only Qwen configuration and actual wire format; no paid dispatch."""
import io
import json
from unittest import TestCase
from unittest.mock import patch
from flask import Flask
from PIL import Image
from core.config import AppConfig,ConfigError,validate_flask_config
from services.service_factory import homework_vision_provider, build_ai_vision_provider_from_config


class QwenHomeworkProviderTests(TestCase):
    def config(self):
        return {'AI_PROVIDER':'kimi','AI_API_KEY':'fake-care','AI_BASE_URL':'https://care.invalid/v1',
            'AI_VISION_MODEL':'kimi-k2.6','AI_VISION_ENABLED':True,
            'AI_VISION_MAX_BYTES':524288,'AI_VISION_MAX_DIMENSION':1280,
            'AI_VISION_TIMEOUT_SECONDS':17,
            'HOMEWORK_VISION_PROVIDER':'qwen','HOMEWORK_VISION_API_KEY':'fake-paper',
            'HOMEWORK_VISION_BASE_URL':'https://paper.invalid/compatible-mode/v1',
            'HOMEWORK_VISION_MODEL':'qwen3-vl-plus','HOMEWORK_VISION_MAX_BYTES':8388608,
            'HOMEWORK_VISION_MAX_DIMENSION':3200,'HOMEWORK_VISION_TIMEOUT_SECONDS':120}

    def test_paper_override_does_not_change_existing_care_configuration(self):
        app=Flask(__name__);app.config.update(self.config());before=dict(app.config)
        with app.app_context():
            paper=homework_vision_provider();care=build_ai_vision_provider_from_config(app.config)
        self.assertEqual(dict(app.config),before)
        self.assertEqual((paper.provider_name,paper.model_name,paper.max_image_dimension),('qwen','qwen3-vl-plus',3200))
        self.assertEqual((care.provider_name,care.model_name,care.max_image_dimension),('moonshot','kimi-k2.6',1280))
        self.assertTrue(paper.json_output);self.assertFalse(care.json_output)
        self.assertTrue(paper.capture_received_response);self.assertFalse(care.capture_received_response)
        self.assertEqual((paper.timeout_seconds,care.timeout_seconds),(120,17))

    def test_paper_timeout_can_change_without_camera_timeout_or_config_mutation(self):
        app=Flask(__name__);app.config.update(self.config());app.config['HOMEWORK_VISION_TIMEOUT_SECONDS']=240
        before=dict(app.config)
        with app.app_context():
            paper=homework_vision_provider();care=build_ai_vision_provider_from_config(app.config)
        self.assertEqual((paper.timeout_seconds,care.timeout_seconds),(240,17))
        self.assertEqual(dict(app.config),before)
        del app.config['HOMEWORK_VISION_TIMEOUT_SECONDS']
        with app.app_context():self.assertEqual(homework_vision_provider().timeout_seconds,120)

    def test_timeout_env_default_and_validation_boundaries(self):
        with patch.dict('os.environ',{},clear=True):
            self.assertEqual(AppConfig.from_env().HOMEWORK_VISION_TIMEOUT_SECONDS,120)
        with patch.dict('os.environ',{'HOMEWORK_VISION_TIMEOUT_SECONDS':'155.5'}):
            self.assertEqual(AppConfig.from_env().HOMEWORK_VISION_TIMEOUT_SECONDS,155.5)
        for invalid in (4,301,True,'120',float('inf'),float('nan')):
            with self.subTest(invalid=invalid),self.assertRaisesRegex(ConfigError,'HOMEWORK_VISION_TIMEOUT_SECONDS'):
                validate_flask_config({'HOMEWORK_VISION_TIMEOUT_SECONDS':invalid})
        base=AppConfig.from_env().to_flask_config()
        for valid in (5,120,155.5,300):
            with self.subTest(valid=valid):
                validate_flask_config({**base,'HOMEWORK_VISION_TIMEOUT_SECONDS':valid})

    def test_unconfigured_paper_key_never_reuses_care_credential(self):
        app=Flask(__name__);app.config.update(self.config());app.config['HOMEWORK_VISION_API_KEY']=''
        with app.app_context():paper=homework_vision_provider()
        self.assertEqual(paper.provider_name,'unconfigured')

    def test_blank_dedicated_key_uses_existing_qwen_key(self):
        with patch.dict('os.environ',{'HOMEWORK_VISION_API_KEY':'','DASHSCOPE_API_KEY':'','QWEN_API_KEY':'fake-qwen','TTS_QWEN_API_KEY':'fake-tts'}):
            self.assertEqual(AppConfig.from_env().HOMEWORK_VISION_API_KEY,'fake-qwen')

    def test_qwen_request_has_json_and_non_thinking_wire_parameters(self):
        app=Flask(__name__);app.config.update(self.config())
        with app.app_context():paper=homework_vision_provider()
        image=io.BytesIO();Image.new('RGB',(640,640),'white').save(image,format='PNG')
        reply=io.BytesIO(json.dumps({'choices':[{'message':{'content':'{"pageReadable":true,"items":[]}'}}]}).encode())
        with patch('urllib.request.urlopen',return_value=reply) as transport:
            result=paper.analyze_image(system_prompt='Return JSON.',user_prompt='Transcribe JSON.',image_bytes=image.getvalue(),content_type='image/png',max_tokens=7000)
        request=transport.call_args.args[0];payload=json.loads(request.data)
        self.assertEqual(payload['response_format'],{'type':'json_object'})
        self.assertIs(payload['enable_thinking'],False);self.assertNotIn('thinking',payload)
        self.assertEqual(payload['max_tokens'],7000);self.assertEqual(result.model,'qwen3-vl-plus')
        self.assertIsInstance(result.raw_response,bytes)
        self.assertEqual(transport.call_args.kwargs['timeout'],120)
        self.assertTrue(payload['messages'][1]['content'][1]['image_url']['url'].startswith('data:image/'))
