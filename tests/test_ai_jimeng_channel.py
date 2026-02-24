import copy
import unittest
from unittest.mock import patch

import requests

from core.ai_service import generate_images_with_jimeng
from core.config import cfg


class _MockResponse:
    def __init__(self, status_code=200, payload=None, text=''):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class JimengChannelTestCase(unittest.TestCase):
    def setUp(self):
        self._origin_ai = copy.deepcopy(cfg.config.get('ai', {}))
        cfg.config.setdefault('ai', {})
        cfg.config['ai'].setdefault('jimeng', {})

    def tearDown(self):
        cfg.config['ai'] = self._origin_ai

    def _set_jimeng(self, **kwargs):
        cfg.config.setdefault('ai', {})
        cfg.config['ai'].setdefault('jimeng', {})
        cfg.config['ai']['jimeng'].update(kwargs)

    def test_local_channel_success(self):
        self._set_jimeng(
            channel='local',
            local_base_url='http://127.0.0.1:5100',
            local_endpoint='/v1/images/generations',
            local_model='jimeng-4.5',
        )

        with patch('core.ai_service.requests.post', return_value=_MockResponse(payload={'data': [{'url': 'https://img.local/1.png'}]})) as post_mock:
            with patch('core.ai_service._generate_images_with_jimeng_api', return_value=([], '')) as api_mock:
                urls, notice = generate_images_with_jimeng(['test prompt'])

        self.assertEqual(urls, ['https://img.local/1.png'])
        self.assertIn('local', notice)
        self.assertEqual(post_mock.call_count, 1)
        api_mock.assert_not_called()

    def test_local_unreachable_should_fallback_to_api(self):
        self._set_jimeng(
            channel='local',
            local_base_url='http://127.0.0.1:5100',
            local_endpoint='/v1/images/generations',
        )

        with patch('core.ai_service.requests.post', side_effect=requests.exceptions.ConnectionError('connection refused')):
            with patch('core.ai_service._generate_images_with_jimeng_api', return_value=(['https://img.api/fallback.png'], 'api 生图成功')) as api_mock:
                urls, notice = generate_images_with_jimeng(['test prompt'])

        self.assertEqual(urls, ['https://img.api/fallback.png'])
        self.assertIn('回退', notice)
        api_mock.assert_called_once()

    def test_local_should_try_multiple_base_urls(self):
        self._set_jimeng(
            channel='local',
            local_base_urls='http://127.0.0.1:5100,http://localhost:5100',
            local_base_url='http://127.0.0.1:5100',
            local_endpoint='/v1/images/generations',
            local_model='jimeng-4.5',
        )

        def _side_effect(url, **kwargs):
            if '127.0.0.1:5100' in str(url):
                raise requests.exceptions.ConnectionError('connection refused')
            return _MockResponse(payload={'data': [{'url': 'https://img.local/5100.png'}]})

        with patch('core.ai_service.requests.post', side_effect=_side_effect) as post_mock:
            with patch('core.ai_service._generate_images_with_jimeng_api', return_value=([], '')) as api_mock:
                urls, notice = generate_images_with_jimeng(['test prompt'])

        self.assertEqual(urls, ['https://img.local/5100.png'])
        self.assertIn('local', notice)
        self.assertGreaterEqual(post_mock.call_count, 2)
        api_mock.assert_not_called()

    def test_api_channel_should_skip_local(self):
        self._set_jimeng(channel='api')

        with patch('core.ai_service.requests.post') as post_mock:
            with patch('core.ai_service._generate_images_with_jimeng_api', return_value=(['https://img.api/1.png'], 'api 生图成功')) as api_mock:
                urls, notice = generate_images_with_jimeng(['test prompt'])

        self.assertEqual(urls, ['https://img.api/1.png'])
        self.assertIn('api', notice)
        post_mock.assert_not_called()
        api_mock.assert_called_once()


if __name__ == '__main__':
    unittest.main()
