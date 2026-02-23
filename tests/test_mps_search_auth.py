import unittest
from unittest.mock import patch, ANY

from fastapi import HTTPException

from core.db import DB
try:
    from apis.mps import search_mp
    _IMPORT_ERROR = None
except Exception as e:  # pragma: no cover
    search_mp = None
    _IMPORT_ERROR = e


@unittest.skipIf(search_mp is None, f"skip mps tests: {_IMPORT_ERROR}")
class MpsSearchAuthTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        DB.create_tables()

    async def test_search_mp_should_use_current_user_auth(self):
        with patch("apis.mps.get_token_cookie", return_value=("token-u1", "cookie-u1")) as get_auth:
            with patch("apis.mps.search_Biz", return_value={"list": [{"nickname": "demo"}], "total": 1}) as wx_search:
                result = await search_mp(
                    kw="demo",
                    limit=10,
                    offset=0,
                    current_user={"username": "u1"},
                )

        self.assertEqual(result.get("code"), 0)
        get_auth.assert_called_once()
        wx_search.assert_called_once_with(
            "demo",
            limit=10,
            offset=0,
            token="token-u1",
            cookie="cookie-u1",
            user_agent=ANY,
        )

    async def test_search_mp_should_raise_when_auth_missing(self):
        with patch("apis.mps.get_token_cookie", return_value=("", "")):
            with self.assertRaises(HTTPException) as ctx:
                await search_mp(
                    kw="demo",
                    limit=10,
                    offset=0,
                    current_user={"username": "u1"},
                )
        self.assertEqual(ctx.exception.status_code, 201)
        detail = ctx.exception.detail or {}
        self.assertIn("重新扫码授权", str(detail.get("message", "")))

    async def test_search_mp_should_not_force_reauth_for_non_auth_errors(self):
        with patch("apis.mps.get_token_cookie", return_value=("token-u1", "cookie-u1")):
            with patch("apis.mps.search_Biz", side_effect=RuntimeError("wx frequency limit")):
                with self.assertRaises(HTTPException) as ctx:
                    await search_mp(
                        kw="demo",
                        limit=10,
                        offset=0,
                        current_user={"username": "u1"},
                    )
        self.assertEqual(ctx.exception.status_code, 201)
        detail = ctx.exception.detail or {}
        msg = str(detail.get("message", ""))
        self.assertIn("搜索公众号失败", msg)
        self.assertNotIn("重新扫码授权", msg)


if __name__ == "__main__":
    unittest.main()
