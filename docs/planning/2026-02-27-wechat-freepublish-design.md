# 微信草稿箱同步 + 群发功能设计

日期：2026-02-27

## 背景

在现有"自动创作并同步到微信公众号草稿箱"功能基础上，增加"同步且立即群发"选项，让用户可以选择同步后自动触发微信群发接口。

## 决策记录

| 问题 | 决策 |
|------|------|
| 群发触发时机 | 全自动：草稿同步成功后立即调用群发接口 |
| 群发失败处理 | 发站内信通知，不重试（与 CSDN 失败处理一致） |
| 配置字段形式 | 枚举字段 `auto_compose_wechat_mode`，替代布尔值 |

## 数据模型

**`core/models/message_task.py`** 新增字段：

```python
auto_compose_wechat_mode = Column(String(32), default="draft_only")
# "draft_only"        — 仅同步到草稿箱（现有行为，默认值）
# "draft_and_publish" — 同步草稿箱后立即触发群发
```

- 保留 `auto_compose_sync_enabled` 作为总开关
- 存量任务默认 `"draft_only"`，行为不变，无需数据迁移

## 服务层

**`core/wechat_draft_service.py`** 新增方法：

```python
def freepublish_submit(self, media_id: str) -> str:
    """
    调用 POST /cgi-bin/freepublish/submit 提交群发任务
    Returns: publish_id（微信异步任务ID）
    Raises: Exception（errcode != 0 时）
    """
```

微信接口说明：
- 端点：`POST https://api.weixin.qq.com/cgi-bin/freepublish/submit`
- 入参：`{"media_id": "<草稿media_id>"}`
- 响应：`{"errcode": 0, "publish_id": "...", "msg_data_id": "..."}`
- 群发为异步任务，成功提交 ≠ 发布完成

**`jobs/mps.py`** 在 `_run_auto_compose_sync` 草稿同步成功后追加逻辑：

```python
media_id = (raw or {}).get("media_id", "")
wechat_mode = str(getattr(task, "auto_compose_wechat_mode", "") or "draft_only")

if synced and wechat_mode == "draft_and_publish" and media_id:
    try:
        svc = WechatDraftService(wechat_app_id, wechat_app_secret)
        publish_id = svc.freepublish_submit(media_id)
        # log + 站内信：群发已提交成功
    except Exception as e:
        # log + 站内信：群发提交失败
        create_notice(..., title="微信群发提交失败", content=str(e))
```

## API 层

**`apis/message_task.py`** create/update 接口：

```python
auto_compose_wechat_mode = body.get("auto_compose_wechat_mode", "draft_only")
if auto_compose_wechat_mode not in ("draft_only", "draft_and_publish"):
    auto_compose_wechat_mode = "draft_only"
task.auto_compose_wechat_mode = auto_compose_wechat_mode
```

## 前端

任务编辑页（`auto_compose_sync_enabled` 开关开启后展示）：

```
[✓] 启用自动创作并同步到微信公众号

    同步模式：
    ◉ 仅同步草稿箱
    ○ 同步且立即群发  ⚠️ 发布后粉丝可见，请确认内容无误
```

- 开关关闭时 Radio Group 隐藏
- 默认选中"仅同步草稿箱"

## 涉及文件

1. `core/models/message_task.py` — 新增 `auto_compose_wechat_mode` 字段
2. `core/wechat_draft_service.py` — 新增 `freepublish_submit()` 方法
3. `jobs/mps.py` — 群发触发逻辑
4. `apis/message_task.py` — 字段读写与校验
5. `web_ui/src/views/`（任务编辑页）— Radio Group UI
