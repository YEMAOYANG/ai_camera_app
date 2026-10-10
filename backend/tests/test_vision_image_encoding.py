"""Image budget regression tests use generated pixels only, without HTTP."""
import base64
import io
import json
import random
from unittest import TestCase
from unittest.mock import patch

from PIL import Image
from integrations.ai.kimi_vision_provider import OpenAICompatibleVisionProvider,_encode_image


def synthetic_png(size,seed=1):
    random_pixels=random.Random(seed).randbytes(size[0]*size[1]*3)
    image=Image.frombytes('RGB',size,random_pixels)
    output=io.BytesIO();image.save(output,format='PNG');return output.getvalue()


def decoded(value):
    prefix,body=value.split(',',1)
    return prefix,base64.b64decode(body,validate=True)


class VisionImageEncodingTests(TestCase):
    def provider(self,**kwargs):
        return OpenAICompatibleVisionProvider(provider_name='qwen',api_key='fake',base_url='https://invalid.example/v1',
            model_name='qwen3-vl-plus',**kwargs)

    def test_large_complete_png_is_decoded_before_eight_megabyte_budget(self):
        body=synthetic_png((1800,1600))
        self.assertGreater(len(body),8388608)
        value=_encode_image(body,'image/png',8388608,max_dimension=3200,jpeg_quality=95)
        prefix,compressed=decoded(value)
        self.assertEqual(prefix,'data:image/jpeg;base64');self.assertLessEqual(len(compressed),8388608)
        with Image.open(io.BytesIO(compressed)) as image:
            image.load();self.assertEqual(image.size,(1800,1600));self.assertEqual(image.format,'JPEG')

    def test_over_budget_jpeg_progressively_reduces_quality_without_truncating(self):
        body=synthetic_png((512,512))
        high=decoded(_encode_image(body,'image/png',1000000,max_dimension=512,jpeg_quality=95))[1]
        low=decoded(_encode_image(body,'image/png',100000,max_dimension=512,jpeg_quality=95))[1]
        self.assertGreater(len(high),100000);self.assertLessEqual(len(low),100000)
        with Image.open(io.BytesIO(low)) as image:image.load();self.assertEqual(image.size,(512,512))

    def test_small_image_preserves_existing_camera_resize_and_quality_bytes(self):
        body=synthetic_png((900,500))
        with Image.open(io.BytesIO(body)) as source:
            expected=source.convert('RGB');expected.thumbnail((640,640))
            buffer=io.BytesIO();expected.save(buffer,format='JPEG',quality=85,optimize=True)
        actual=decoded(_encode_image(body,'image/png',524288,max_dimension=640,jpeg_quality=85))[1]
        self.assertEqual(actual,buffer.getvalue())

    def test_no_pillow_corrupt_truncated_and_uncompressible_images_never_send(self):
        provider=self.provider(max_bytes=8192,max_image_dimension=256)
        body=synthetic_png((256,256))
        inputs=(b'',b'not an image',body[:8192],body)
        with patch('urllib.request.urlopen') as transport:
            for value in inputs:
                with self.subTest(length=len(value)):
                    self.assertIsNone(provider.analyze_image(system_prompt='JSON',user_prompt='JSON',image_bytes=value,content_type='image/png'))
            with patch('integrations.ai.kimi_vision_provider.Image',None):
                self.assertIsNone(provider.analyze_image(system_prompt='JSON',user_prompt='JSON',image_bytes=body,content_type='image/png'))
            transport.assert_not_called()

    def test_normal_request_contains_valid_budgeted_jpeg(self):
        provider=self.provider(max_bytes=524288,max_image_dimension=1280)
        body=synthetic_png((400,300))
        response=io.BytesIO(json.dumps({'choices':[{'message':{'content':'{}'}}]}).encode())
        with patch('urllib.request.urlopen',return_value=response) as transport:
            self.assertIsNotNone(provider.analyze_image(system_prompt='JSON',user_prompt='JSON',image_bytes=body,content_type='image/png'))
        sent=json.loads(transport.call_args.args[0].data)['messages'][1]['content'][1]['image_url']['url']
        prefix,compressed=decoded(sent);self.assertEqual(prefix,'data:image/jpeg;base64')
        self.assertLessEqual(len(compressed),provider.max_bytes)
        with Image.open(io.BytesIO(compressed)) as image:image.verify()
