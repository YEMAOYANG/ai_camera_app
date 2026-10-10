"""Independent grader/teacher configuration and wire contract; no paid calls."""
import io
import json
from unittest import TestCase
from unittest.mock import patch

from flask import Flask
from PIL import Image

from core.config import AppConfig, ConfigError, validate_flask_config
from core.errors import ApiError
from services.service_factory import (
    build_ai_vision_provider_from_config, homework_grading_provider,
    homework_tutor_provider, homework_vision_provider,
)


class HomeworkProviderIsolationTests(TestCase):
    def config(self):
        return {
            'AI_PROVIDER':'kimi','AI_API_KEY':'fake-camera-key',
            'AI_BASE_URL':'https://care.invalid/v1','AI_VISION_MODEL':'kimi-k2.6',
            'AI_VISION_ENABLED':True,'AI_VISION_MAX_DIMENSION':1280,
            'HOMEWORK_VISION_PROVIDER':'qwen','HOMEWORK_VISION_API_KEY':'fake-paper-key',
            'HOMEWORK_VISION_BASE_URL':'https://paper.invalid/v1','HOMEWORK_VISION_MODEL':'qwen3-vl-plus',
            'HOMEWORK_TUTOR_PROVIDER':'deepseek','HOMEWORK_TUTOR_API_KEY':'fake-teacher-key',
            'HOMEWORK_TUTOR_BASE_URL':'https://teacher.invalid/v1','HOMEWORK_TUTOR_MODEL':'deepseek-flash',
        }

    def test_grader_teacher_and_camera_have_separate_configuration(self):
        app=Flask(__name__);app.config.update(self.config());before=dict(app.config)
        with app.app_context():
            teacher=homework_tutor_provider();paper=homework_vision_provider()
            camera=build_ai_vision_provider_from_config(app.config)
            self.assertIsNone(homework_grading_provider())
        self.assertEqual((teacher.provider_name,teacher.model_name),('deepseek','deepseek-flash'))
        self.assertEqual(teacher.api_key,'fake-teacher-key')
        self.assertEqual((paper.provider_name,paper.model_name),('qwen','qwen3-vl-plus'))
        self.assertEqual((camera.provider_name,camera.model_name),('moonshot','kimi-k2.6'))
        self.assertEqual(dict(app.config),before)
        self.assertTrue(teacher.capture_received_response)
        self.assertFalse(camera.capture_received_response)

    def test_unset_teacher_preserves_paper_provider_even_with_tencent_grading(self):
        app=Flask(__name__);app.config.update(self.config())
        app.config.update(HOMEWORK_TUTOR_PROVIDER='',HOMEWORK_GRADING_PROVIDER='tencent')
        with app.app_context():teacher=homework_tutor_provider()
        self.assertEqual((teacher.provider_name,teacher.model_name),('qwen','qwen3-vl-plus'))

    def test_explicit_teacher_without_key_does_not_reuse_camera_or_paper_keys(self):
        app=Flask(__name__);app.config.update(self.config());app.config['HOMEWORK_TUTOR_API_KEY']=''
        with app.app_context():self.assertEqual(homework_tutor_provider().provider_name,'unconfigured')

    def test_deepseek_pro_cannot_receive_images_or_be_enabled_for_camera(self):
        config=self.config();config['HOMEWORK_TUTOR_MODEL']='deepseek-v4-pro'
        app=Flask(__name__);app.config.update(config)
        with app.app_context():self.assertEqual(homework_tutor_provider().provider_name,'unconfigured')
        config.update(AI_PROVIDER='deepseek',AI_VISION_MODEL='deepseek-flash')
        self.assertEqual(build_ai_vision_provider_from_config(config).provider_name,'unconfigured')

    def test_deepseek_flash_json_non_thinking_wire_and_received_journal(self):
        app=Flask(__name__);app.config.update(self.config())
        with app.app_context():teacher=homework_tutor_provider()
        image=io.BytesIO();Image.new('RGB',(640,640),'white').save(image,format='PNG')
        raw=json.dumps({'choices':[{'message':{'content':'{"teacherText":"看原图"}'},'finish_reason':'stop'}]}).encode()
        with patch('urllib.request.urlopen',return_value=io.BytesIO(raw)) as transport:
            result=teacher.analyze_image(system_prompt='Return JSON.',user_prompt='Explain.',
                image_bytes=image.getvalue(),content_type='image/png',max_tokens=4000,temperature=.6)
        payload=json.loads(transport.call_args.args[0].data)
        self.assertEqual(payload['model'],'deepseek-flash')
        self.assertEqual(payload['thinking'],{'type':'disabled'})
        self.assertEqual(payload['response_format'],{'type':'json_object'})
        self.assertNotIn('enable_thinking',payload)
        self.assertEqual(result.raw_response,raw)
        self.assertEqual(transport.call_args.kwargs['timeout'],120)

    def test_tencent_factory_selects_only_grader_and_hides_configuration_errors(self):
        app=Flask(__name__);app.config.update(self.config());app.config['HOMEWORK_GRADING_PROVIDER']='tencent'
        from integrations.ai.tencent_homework_provider import TencentConfigurationError
        fake=object()
        with app.app_context(),patch('integrations.ai.tencent_homework_provider.TencentHomeworkProvider.from_config',return_value=fake) as factory:
            self.assertIs(homework_grading_provider(),fake)
            self.assertIs(factory.call_args.args[0],app.config)
        with app.app_context(),patch('integrations.ai.tencent_homework_provider.TencentHomeworkProvider.from_config',side_effect=TencentConfigurationError('CredentialsPairRequired')):
            with self.assertRaises(ApiError) as failure:homework_grading_provider()
        self.assertEqual(failure.exception.code,'homework_provider_unconfigured')

    def test_env_defaults_keep_legacy_and_explicit_flash_has_scoped_defaults(self):
        with patch.dict('os.environ',{},clear=True):
            config=AppConfig.from_env()
            self.assertEqual(config.HOMEWORK_GRADING_PROVIDER,'')
            self.assertEqual(config.HOMEWORK_TUTOR_PROVIDER,'')
            self.assertEqual(config.HOMEWORK_TUTOR_API_KEY,'')
            validate_flask_config(config.to_flask_config())
        with patch.dict('os.environ',{'HOMEWORK_TUTOR_PROVIDER':'deepseek','DEEPSEEK_API_KEY':'fake-deepseek'},clear=True):
            config=AppConfig.from_env()
            self.assertEqual(config.HOMEWORK_TUTOR_MODEL,'deepseek-flash')
            self.assertEqual(config.HOMEWORK_TUTOR_BASE_URL,'https://api.deepseek.com')
            self.assertEqual(config.HOMEWORK_TUTOR_API_KEY,'fake-deepseek')
            validate_flask_config(config.to_flask_config())
        with patch.dict('os.environ',{'HOMEWORK_TENCENT_SECRET_ID':'dedicated-id','TENCENTCLOUD_SECRET_ID':'standard-id','TENCENTCLOUD_SECRET_KEY':'standard-key'},clear=True):
            config=AppConfig.from_env()
            self.assertEqual(config.HOMEWORK_TENCENT_SECRET_ID,'dedicated-id')
            self.assertEqual(config.HOMEWORK_TENCENT_SECRET_KEY,'')

    def test_scoped_configuration_validation(self):
        for value in (4,121,True,'30',float('inf'),float('nan')):
            with self.subTest(value=value),self.assertRaisesRegex(ConfigError,'HOMEWORK_TENCENT_TIMEOUT_SECONDS'):
                validate_flask_config({'HOMEWORK_TENCENT_TIMEOUT_SECONDS':value})
        with self.assertRaisesRegex(ConfigError,'HOMEWORK_GRADING_PROVIDER'):
            validate_flask_config({'HOMEWORK_GRADING_PROVIDER':'deepseek'})
        with self.assertRaisesRegex(ConfigError,'image-capable'):
            validate_flask_config({'HOMEWORK_TUTOR_PROVIDER':'deepseek','HOMEWORK_TUTOR_MODEL':'deepseek-v4-pro'})
