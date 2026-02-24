import unittest
from unittest.mock import patch

from core.ai_service import publish_batch_to_wechat_draft


class _MockResp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = ""

    def json(self):
        return self._payload


class AIWechatPublishErrorTestCase(unittest.TestCase):
    BODY_WITH_IMAGE = "![img](https://mmbiz.qpic.cn/sz_mmbiz_png/demo.png)"

    @patch("core.ai_service._try_upload_cover_media_id", return_value=("", ""))
    @patch("core.ai_service._wechat_auth", return_value=("token", "cookie"))
    @patch("core.ai_service.requests.post")
    def test_publish_should_report_auth_expired_from_base_resp(self, post_mock, *_):
        post_mock.return_value = _MockResp(
            status_code=200,
            payload={
                "base_resp": {
                    "ret": 200003,
                    "err_msg": "invalid session",
                }
            },
        )
        ok, message, _ = publish_batch_to_wechat_draft(
            [{"title": "t", "content": self.BODY_WITH_IMAGE}],
            owner_id="u1",
            session=object(),
        )
        self.assertFalse(ok)
        self.assertIn("微信授权已失效", message)
        self.assertIn("ret=200003", message)

    @patch("core.ai_service._try_upload_cover_media_id", return_value=("", ""))
    @patch("core.ai_service._wechat_auth", return_value=("token", "cookie"))
    @patch("core.ai_service.requests.post")
    def test_publish_should_not_return_plain_unknown_error(self, post_mock, *_):
        post_mock.return_value = _MockResp(
            status_code=200,
            payload={
                "ret": -1,
                "base_resp": {"ret": -1},
                "foo": "bar",
            },
        )
        ok, message, _ = publish_batch_to_wechat_draft(
            [{"title": "t", "content": self.BODY_WITH_IMAGE}],
            owner_id="u1",
            session=object(),
        )
        self.assertFalse(ok)
        self.assertIn("微信草稿箱投递失败", message)
        self.assertIn("ret=-1", message)
        self.assertIn("payload=", message)

    @patch("core.ai_service._try_upload_cover_media_id", return_value=("", "cover failed"))
    @patch("core.ai_service._wechat_auth", return_value=("token", "cookie"))
    @patch("core.ai_service.requests.post")
    def test_publish_should_retry_without_cover_when_ret_64513(self, post_mock, *_):
        post_mock.side_effect = [
            _MockResp(
                status_code=200,
                payload={
                    "ret": 64513,
                    "errmsg": "封面必须存在正文中，请检查封面",
                },
            ),
            _MockResp(
                status_code=200,
                payload={
                    "ret": 0,
                },
            ),
        ]
        ok, message, _ = publish_batch_to_wechat_draft(
            [{"title": "t", "content": self.BODY_WITH_IMAGE, "cover_url": "https://demo"}],
            owner_id="u1",
            session=object(),
        )
        self.assertTrue(ok)
        self.assertIn("自动移除封面重试成功", message)


if __name__ == "__main__":
    unittest.main()
