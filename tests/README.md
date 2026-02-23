# Tests 目录说明

本目录统一存放项目测试与联调脚本，按用途分为两类：

- `test_*.py`（`unittest`）：可直接纳入自动化回归
- 手工联调脚本：保留 `test_` 前缀用于历史兼容，但默认不建议通过 `discover` 全量执行

## 推荐执行方式

运行核心自动化测试：

```bash
python3.10 -m unittest \
  tests.test_plan_service \
  tests.test_ai_draftbox \
  tests.test_ai_publish_queue \
  tests.test_billing_flow \
  tests.test_wechat_auth_service \
  tests.test_ai_mock_provider \
  tests.test_user_admin_api \
  tests.test_ai_activity_metrics \
  tests.test_template_parser
```

手动运行即梦联调脚本：

```bash
export JIMENG_AK='your-ak'
export JIMENG_SK='your-sk'
python tests/test_jimeng_api.py --scene article_cover --topic "自媒体增长" --style "极简商业"
```
