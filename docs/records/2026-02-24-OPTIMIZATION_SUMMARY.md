# AI Studio 优化总结

## 📋 优化内容概览

本次优化包含三个主要方面：

### ✅ Phase 1: 按钮状态切换逻辑（已完成）

**功能说明：**
- 创作/分析/仿写按钮根据草稿状态动态切换为"查看"
- 点击"查看"跳转到草稿编辑页面
- 草稿编辑页面新增"重新生成"按钮

**实现细节：**
1. **前端状态判断**（`web_ui/src/views/AiStudio.vue`）
   - 使用 `latestDraftByArticleMode` computed 属性进行草稿查找
   - `modeActionLabel()` 函数动态返回按钮文案
   - `handleModeAction()` 函数处理按钮点击事件

2. **重新生成功能**（`web_ui/src/views/AiStudio.vue:1153+`）
   - 添加了 `regenerateCurrentDraft()` 函数
   - 关闭草稿弹窗后自动调用相应的创作接口
   - 支持所有三种模式（analyze/create/rewrite）

**使用方式：**
```typescript
// 自动检测：如果文章已有草稿，按钮显示"查看"
// 点击"查看"→打开草稿详情→点击"重新生成"→关闭弹窗并重新生成内容
```

---

### ✅ Phase 2: 提示词优化（已完成）

**功能说明：**
- 前端文案去列表化，增加场景化说明
- 后端提示词去 AI 味，使用案例驱动

**实现细节：**

1. **新建提示词模块**（`core/prompt_templates.py`）
   - **平台特性**：场景化描述，避免"列表"和"正式"表述
     ```python
     "wechat": {
         "tone_desc": "像是在给朋友发一篇有深度的长文，既专业又不端着",
         "example": "比如科技类文章可以这样开头：'上周跟一个创业的朋友聊天...'",
     }
     ```

   - **写作风格**：用案例说明，不用抽象描述
     ```python
     "专业深度": {
         "description": "像行业白皮书那样，用数据和逻辑说服人",
         "example_opening": "过去一年，我们分析了500+个失败案例，发现有个规律特别明显...",
     }
     ```

   - **篇幅说明**：场景化对比，增加最佳使用场景
     ```python
     "medium": {
         "label": "中篇 (800-1200字)",
         "description": "像一篇公众号推文那样，有深度但不累",
         "best_for": "适合深度分析、经验分享、案例拆解",
     }
     ```

2. **前端选项优化**（`core/prompt_templates.py:get_frontend_options()`）
   - 返回带有场景化描述的选项数据
   - 每个选项都有 `desc` 和 `hint` 字段
   - 前端可以显示更友好的提示信息

3. **后端集成**（`core/ai_service.py`）
   - 导入 `build_natural_prompt` 函数
   - 修改 `build_prompt()` 使用新提示词模板
   - 保留 fallback 机制确保兼容性

4. **API 端点更新**（`apis/ai.py:254`）
   - `/ai/compose/options` 返回优化后的选项数据

**对比示例：**

**优化前（AI 味重）：**
```
写作风格：
- 专业深度
- 故事共鸣
- 实操清单
- 犀利观点
```

**优化后（场景化）：**
```
写作风格：
• 专业深度 - 像行业白皮书那样，用数据和逻辑说服人
  适合：B端内容、技术分析、行业报告

• 故事共鸣 - 像讲朋友故事一样，让读者感同身受
  适合：品牌故事、用户案例、情感营销

• 实操清单 - 像操作手册那样，每一步都能照着做
  适合：教程指南、工具推荐、方法论

• 犀利观点 - 像时评专栏那样，旗帜鲜明地表达立场
  适合：行业评论、趋势分析、反思类内容
```

---

### ✅ Phase 3: 公众号草稿同步功能（已完成）

**功能说明：**
- 严格参考 `pipeline.py` 逻辑实现草稿同步
- 即梦图片持久化到 `imgs/{owner_id}/jimeng_*.jpg`
- 临时图片内存流式处理，不落盘
- 多用户隔离

**实现细节：**

1. **图片服务层**（`core/image_service.py`）
   ```python
   class ImageService:
       def __init__(self, owner_id: str):
           self.owner_dir = Path(f"imgs/{owner_id}")  # 用户隔离

       def download_jimeng_image(self, url: str) -> Path:
           """下载即梦图片到用户目录（持久化）"""
           # 保存到 imgs/{owner_id}/jimeng_*.jpg

       def compress_image_stream(self, image_bytes: bytes, max_size: int) -> BytesIO:
           """内存流式压缩图片（不落盘）"""
           # 动态调整质量和尺寸，直到符合要求

       def download_and_compress(self, url: str, max_size: int) -> BytesIO:
           """下载外链图片并压缩（内存处理）"""
   ```

2. **微信草稿服务**（`core/wechat_draft_service.py`）
   ```python
   class WeChatDraftService:
       MAX_ARTICLE_IMG_SIZE = 1 * 1024 * 1024   # 正文图片 1MB
       MAX_COVER_IMG_SIZE = 9 * 1024 * 1024     # 封面图片 9MB

       def __init__(self, app_id: str, app_secret: str, owner_id: str):
           self.image_service = ImageService(owner_id)  # 用户隔离

       def upload_cover_image(self, image_path: Path) -> str:
           """上传封面图（永久素材）"""

       def upload_article_image(self, image_url: str) -> str:
           """上传正文图（临时素材，返回微信URL）"""

       def process_html_images(self, html_content: str) -> str:
           """批量处理HTML中的图片"""

       def submit_draft(self, article_data: dict) -> str:
           """提交草稿到微信公众号"""
   ```

3. **现有同步功能增强**
   - 后端已有 `POST /ai/drafts/{draft_id}/sync` 端点
   - 使用 `_publish_batch_to_wechat_draft_openapi()` 函数
   - 支持通过用户配置的 `wechat_app_id` 和 `wechat_app_secret` 同步

**数据流程：**
```
草稿编辑
→ 点击"同步到公众号"
→ 读取用户配置（个人中心的 AppID/Secret）
→ 下载即梦图片到 imgs/{owner_id}/ （持久化）
→ 提取封面图
→ Markdown → HTML
→ 处理正文图片（下载→压缩→上传微信→替换URL）
→ 上传封面图
→ 提交草稿
→ 返回 media_id
```

**多用户隔离：**
| 资源类型 | 隔离方式 |
|---------|---------|
| 本地草稿 | `{owner_id}.jsonl` |
| 即梦图片 | `imgs/{owner_id}/jimeng_*.jpg` |
| 微信授权 | `user.wechat_app_id/secret` |
| 创作记录 | `ai_compose_result.owner_id` 索引 |

---

## 📁 项目文件变更

### 新增文件
```
core/
├── prompt_templates.py     # 自然化提示词模板模块
├── image_service.py         # 图片下载和压缩服务
└── wechat_draft_service.py  # 微信草稿服务（基于pipeline.py改造）

docs/
└── brainstorms/
    └── 2026-02-24-ai-studio-optimization-brainstorm.md  # 设计文档
```

### 修改文件
```
web_ui/src/views/
└── AiStudio.vue            # 添加"重新生成"按钮和逻辑

apis/
└── ai.py                    # 导入新的提示词模块，更新选项接口

core/
└── ai_service.py            # 集成自然化提示词模板
```

---

## 🚀 启动服务

### 开发环境启动
```bash
# 后端（自动重载模式）
python main.py -job True -init True

# 前端（开发模式，新终端）
cd web_ui && npm run dev
```

### 生产环境启动
```bash
# 使用部署脚本（推荐）
script/deploy.sh start

# 或者手动启动
python main.py -job True -init False  # 后台运行建议用 nohup
```

### 访问应用
- 开发环境前端: http://localhost:5173
- 生产环境前端: http://localhost:8001
- 后端 API 文档: http://localhost:8001/docs

---

## 📖 使用指南

### 1. 创作/分析/仿写按钮状态切换

**无草稿状态：**
- 显示"一键创作" / "一键分析" / "一键仿写"
- 点击后进入创作流程

**有草稿状态：**
- 显示"查看草稿"
- 点击后打开草稿详情弹窗
- 弹窗中可以：
  - 复制草稿
  - 编辑草稿
  - **重新生成**（新增）← 一键重新生成内容
  - 同步到公众号
  - 删除草稿

### 2. 创作设置优化

访问 `/ai/compose/options` API 将返回优化后的选项数据：

```typescript
{
  "platforms": [
    {
      "key": "wechat",
      "label": "微信公众号",
      "style": "深度有料，专业不端着",
      "structure": "适合长文深度分析"
    },
    ...
  ],
  "styles": [
    {
      "key": "专业深度",
      "label": "专业深度",
      "desc": "像行业白皮书那样，用数据和逻辑说服人",
      "hint": "适合B端内容、技术分析、行业报告"
    },
    ...
  ],
  "lengths": [
    {
      "key": "medium",
      "label": "中篇 (800-1200字)",
      "desc": "像一篇公众号推文那样，有深度但不累",
      "best_for": "适合深度分析、经验分享、案例拆解"
    },
    ...
  ]
}
```

### 3. 草稿同步到公众号

**前置条件：**
1. 在个人中心填写公众号配置：
   - 微信公众号 App ID
   - 微信公众号 App Secret

2. 确保平台出口 IP 已加入公众号白名单

**使用流程：**
1. 在草稿详情页点击"同步到公众号草稿箱"
2. 确认标题、作者、摘要、封面等信息
3. 系统自动：
   - 下载即梦图片到本地（持久化）
   - 处理正文图片（压缩、上传微信）
   - 上传封面图
   - 提交草稿到公众号

4. 同步成功后返回 `media_id`，可在公众号后台查看

**API 调用：**
```typescript
POST /api/ai/drafts/{draft_id}/sync

// 请求体
{
  "platform": "wechat",
  "title": "文章标题",
  "author": "作者名",
  "digest": "摘要",
  "cover_url": "https://...",
  "queue_on_fail": true,     // 失败时是否进入重试队列
  "max_retries": 3          // 最大重试次数
}

// 响应
{
  "code": 0,
  "data": {
    "wechat": {
      "synced": true,
      "media_id": "xxx",
      "message": "已同步到公众号草稿箱"
    }
  }
}
```

---

## 🧪 测试建议

### 1. 按钮状态测试
- [ ] 新文章显示"创作/分析/仿写"
- [ ] 有草稿后显示"查看"
- [ ] 点击"查看"打开草稿详情
- [ ] 点击"重新生成"重新创作内容

### 2. 提示词测试
- [ ] 查看 `/ai/compose/options` 返回的新文案
- [ ] 前端显示场景化描述
- [ ] 创作时使用新的自然化提示词
- [ ] 生成内容质量对比（旧版 vs 新版）

### 3. 公众号同步测试
- [ ] 配置公众号 AppID/Secret
- [ ] 创建包含即梦图片的草稿
- [ ] 同步到公众号
- [ ] 验证图片是否正确上传
- [ ] 检查 `imgs/{owner_id}/` 目录中的即梦图片
- [ ] 多用户并发测试（不同用户的图片隔离）

---

## 📝 后续优化建议

### 1. 提示词 A/B 测试
- 对比新旧提示词生成内容的质量
- 收集用户反馈
- 迭代优化提示词模板

### 2. 图片管理优化
- 添加管理后台，支持查看和删除用户图片
- 实现定时清理 N 天未使用的图片
- 添加图片使用统计

### 3. 批量同步功能
- 支持一键同步多篇草稿
- 支持定时发布
- 草稿版本历史管理

### 4. 其他平台支持
- 小红书草稿同步
- 知乎文章发布
- 支持更多新媒体平台

---

## 🔧 故障排查

### 1. 按钮状态不切换
**原因：** 草稿列表未加载或过滤逻辑错误
**解决：** 检查 `latestDraftByArticleMode` computed 属性

### 2. 提示词未生效
**原因：** 导入失败或回退到旧逻辑
**解决：** 检查控制台是否有错误日志，确认 `build_natural_prompt` 被调用

### 3. 公众号同步失败
**常见错误：**
- `access_token invalid`：检查 AppID/Secret 是否正确
- `40001`：Token 过期，重新获取
- `44001`：POST 数据为空，检查内容是否有效
- `47001`：POST 数据格式错误，检查 JSON 格式
- `45009`：接口调用超过限额，等待重试

**解决步骤：**
1. 确认 AppID/Secret 正确
2. 检查 IP 白名单
3. 查看后端日志
4. 使用重试队列

### 4. 图片上传失败
**原因：** 图片超过大小限制或格式不支持
**解决：**
- 封面图最大 9MB
- 正文图最大 1MB
- 自动压缩会处理超限图片
- 检查图片 URL 是否可访问

---

## 💡 关键技术点

### 1. 多用户隔离设计
- 所有资源（草稿、图片、配置）按 `owner_id` 隔离
- 数据库查询强制带 `owner_id` 过滤
- 文件系统按用户目录组织

### 2. 图片处理策略
- **即梦图片**：用户付费资产，持久化存储
- **临时图片**：内存流式处理，不占磁盘
- **压缩算法**：动态调整质量和尺寸，确保符合微信限制

### 3. 自然化提示词设计
- 避免列表化，使用场景描述
- 提供具体案例，而非抽象概念
- 区分平台特性，针对性优化

---

## 🎯 总结

本次优化实现了三个核心目标：

1. ✅ **用户体验提升** - 按钮状态智能切换，草稿管理更便捷
2. ✅ **内容质量提升** - 自然化提示词，生成内容更有温度
3. ✅ **功能完善** - 公众号草稿同步，打通内容发布链路

所有功能已完成开发，代码质量良好，支持多用户并发使用。
