---
date: 2026-02-24
topic: ai-studio-optimization
---

# AI Studio 创作体验优化与公众号同步功能

## What We're Building

为 AI Studio 创作中台实现三个核心优化：

1. **提示词去 AI 味改造** - 前端文案和后端系统提示词都改为自然、通俗、案例驱动的表达方式，摆脱生硬的列表化和机器感
2. **智能按钮状态切换** - 创作/分析/仿写按钮根据草稿箱状态动态切换为"查看"，草稿页面支持重新生成
3. **公众号草稿同步** - 严格参考 pipeline.py 的成熟逻辑，实现多用户隔离的草稿同步，包含即梦图片持久化和临时图片内存处理

## Why This Approach

### 选择渐进式重构而非重写

**考虑过的方案：**
- ❌ 微服务拆分 - 当前规模不需要，违反 YAGNI
- ❌ 最小改动 - 无法满足公众号同步的核心需求
- ✅ **渐进式重构** - 在现有架构上逐步增强，模块化改造

**核心优势：**
- 每个模块独立开发和测试，风险可控
- 复用 pipeline.py 的成熟图片处理逻辑
- 不破坏现有功能，可以分阶段上线
- 符合 YAGNI 原则，只解决当前问题

## Key Decisions

### 1. 提示词管理策略

**决策：** 创建独立的 `core/prompt_templates.py` 模块

**理由：**
- 提示词是产品核心竞争力，应独立管理便于迭代
- 支持 A/B 测试不同风格（叙事型/技术型/对话型）
- 可根据平台（微信/小红书/知乎）动态调整

**具体改进点：**

#### 前端文案优化（去 AI 味）

**反例（当前）：**
```
写作风格：
- 专业深度
- 故事共鸣
- 实操清单
- 犀利观点
```

**正例（优化后）：**
```
写作风格：
• 专业深度 - 像行业白皮书那样，用数据和逻辑说服人
• 故事共鸣 - 像讲朋友故事一样，让读者感同身受
• 实操清单 - 像操作手册那样，每一步都能照着做
• 犀利观点 - 像时评专栏那样，旗帜鲜明地表达立场
```

**改进原则：**
- 用"像...那样"提供具体参照物
- 避免抽象词汇堆砌
- 每个选项附带场景化说明

#### 后端提示词优化（去列表化）

**反例（当前可能的样子）：**
```
你是一个专业的内容创作助手。请完成以下任务：
1. 分析文章主题
2. 提炼核心观点
3. 组织文章结构
4. 生成流畅文案
```

**正例（优化后）：**
```
想象你是一位资深的新媒体编辑，正在为朋友的公众号改写一篇文章。
你需要做的是：把原文的核心观点用更生动的方式讲出来。

不要写成论文格式，而是像在微信里跟朋友聊天 - 有故事、有例子、有感情。
举个例子，如果原文说"用户体验优化很重要"，你可以改成"上周我们改了登录页面，
转化率直接涨了30%，这事儿告诉我们..."

目标读者是 {{audience}}，他们关心的是 {{pain_point}}。
```

**改进原则：**
- 用"想象你是..."建立角色代入感
- 用"不要...而是..."明确风格边界
- 提供具体改写案例（few-shot learning）
- 使用变量插入上下文信息

---

### 2. 按钮状态管理机制

**决策：** 纯前端状态管理 + 后端草稿列表过滤

**实现细节：**

```typescript
// web_ui/src/views/AiStudio.vue

interface DraftStatus {
  create: boolean   // 是否有创作草稿
  analyze: boolean  // 是否有分析草稿
  rewrite: boolean  // 是否有仿写草稿
}

// 组件加载时检查草稿状态
async function loadDraftStatus(articleId: string): Promise<DraftStatus> {
  const drafts = await api.getDrafts({
    article_id: articleId
  })

  return {
    create: drafts.some(d => d.mode === 'create'),
    analyze: drafts.some(d => d.mode === 'analyze'),
    rewrite: drafts.some(d => d.mode === 'rewrite')
  }
}

// 动态按钮配置
function getButtonConfig(mode: Mode, hasDraft: boolean) {
  if (hasDraft) {
    return {
      label: '查看草稿',
      icon: 'icon-eye',
      type: 'outline',
      action: () => router.push(`/drafts?article_id=${article.id}&mode=${mode}`)
    }
  } else {
    return {
      label: MODE_LABELS[mode],  // "一键创作" | "一键分析" | "一键仿写"
      icon: 'icon-robot',
      type: 'primary',
      action: () => handleGenerate(mode)
    }
  }
}
```

**草稿编辑页面的重新生成按钮：**

```typescript
// web_ui/src/views/DraftEditor.vue (新建或在现有草稿页面添加)

<template>
  <div class="draft-editor">
    <div class="toolbar">
      <a-button @click="regenerate" :loading="regenerating">
        <icon-refresh /> 重新生成
      </a-button>
      <a-button @click="syncToWechat" type="primary">
        <icon-send /> 同步到公众号
      </a-button>
    </div>

    <a-textarea v-model="draft.content" :rows="20" />
  </div>
</template>

<script setup lang="ts">
async function regenerate() {
  regenerating.value = true
  try {
    // 调用原有的创作接口，但带上 force_refresh=true
    const result = await api.composeArticle(draft.article_id, draft.mode, {
      ...draft.metadata.options,
      force_refresh: true
    })

    // 更新草稿内容
    draft.content = result.result
    await api.updateDraft(draft.id, { content: result.result })

    Message.success('重新生成成功！')
  } finally {
    regenerating.value = false
  }
}
</script>
```

**后端 API 增强：**

```python
# apis/ai.py

@router.get("/ai/drafts")
async def list_drafts(
    article_id: Optional[str] = None,  # 新增过滤参数
    mode: Optional[str] = None,        # 新增过滤参数
    current_user: User = Depends(get_current_user)
):
    """获取草稿列表，支持按文章ID和模式过滤"""
    drafts = list_local_drafts(current_user.username)

    if article_id:
        drafts = [d for d in drafts if d.get('article_id') == article_id]
    if mode:
        drafts = [d for d in drafts if d.get('mode') == mode]

    return drafts
```

---

### 3. 图片存储与处理策略

**决策：** 即梦图片持久化 + 临时图片内存处理

**目录结构：**
```
imgs/
├── {owner_id}/          # 用户目录（多用户隔离）
│   └── jimeng_*.jpg     # 即梦生成的图片（持久化）
└── .gitkeep
```

**理由：**
- ✅ 即梦图片是用户付费资产，应该保留
- ✅ 用户可以在草稿中反复引用同一张图片
- ✅ 临时图片（下载的外链、压缩中间产物）不落盘，节省存储
- ✅ 按用户隔离目录，避免文件冲突

**清理策略：**
- 即梦图片不自动清理（用户资产）
- 如果需要清理，提供管理后台手动清理功能
- 未来可以添加定时任务清理 N 天未使用的图片

---

### 4. 公众号同步流程设计

**决策：** 将 pipeline.py 的 `WeChatDraftHelper` 改造为可复用服务

**核心流程：**

```
用户编辑草稿 → 点击"同步到公众号"
→ 检查微信授权（wechat_app_id/secret）
→ 下载即梦图片（如有）
→ 提取封面图（Markdown 第一张图）
→ 转换 Markdown → HTML
→ 处理正文图片（下载外链 → 压缩 → 上传微信 → 替换 URL）
→ 上传封面图 → 获取 thumb_media_id
→ 提交草稿到微信 → 返回 media_id
→ 更新本地草稿 metadata（记录 media_id）
```

**新建模块：**

#### 4.1 图片服务层
```python
# core/image_service.py

from pathlib import Path
from io import BytesIO
import uuid
import requests
from PIL import Image

class ImageService:
    """图片下载、压缩、处理服务"""

    def __init__(self, owner_id: str):
        self.owner_id = owner_id
        self.owner_dir = Path(f"imgs/{owner_id}")
        self.owner_dir.mkdir(parents=True, exist_ok=True)

    async def download_jimeng_image(self, url: str) -> Path:
        """
        下载即梦图片到用户目录（持久化）

        Args:
            url: 即梦图片 URL

        Returns:
            本地文件路径
        """
        filename = f"jimeng_{uuid.uuid4().hex}.jpg"
        local_path = self.owner_dir / filename

        # 下载图片
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()

        with open(local_path, 'wb') as f:
            f.write(resp.content)

        return local_path

    def compress_image_stream(
        self,
        image_bytes: bytes,
        max_size: int
    ) -> BytesIO:
        """
        内存流式压缩图片（不落盘）

        Args:
            image_bytes: 原始图片字节流
            max_size: 最大文件大小（字节）

        Returns:
            压缩后的字节流
        """
        img = Image.open(BytesIO(image_bytes))
        if img.mode != 'RGB':
            img = img.convert('RGB')

        quality = 85
        scale = 0.9

        while True:
            output = BytesIO()
            img.save(output, format='JPEG', quality=quality)

            if output.tell() <= max_size:
                output.seek(0)
                return output

            if quality > 30:
                quality -= 10
            else:
                width, height = img.size
                img = img.resize(
                    (int(width * scale), int(height * scale)),
                    Image.LANCZOS
                )

    async def download_and_compress(
        self,
        url: str,
        max_size: int
    ) -> BytesIO:
        """
        下载外链图片并压缩（内存处理，不落盘）

        Args:
            url: 图片 URL
            max_size: 最大文件大小

        Returns:
            压缩后的字节流
        """
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()

        return self.compress_image_stream(resp.content, max_size)
```

#### 4.2 微信草稿服务
```python
# core/wechat_draft_service.py

from pathlib import Path
from typing import Dict, List
import requests
import time
from bs4 import BeautifulSoup

class WeChatDraftService:
    """微信公众号草稿箱服务（从 pipeline.py 改造）"""

    # 微信限制
    MAX_ARTICLE_IMG_SIZE = 1 * 1024 * 1024   # 正文图片 1MB
    MAX_COVER_IMG_SIZE = 9 * 1024 * 1024     # 封面图片 9MB

    def __init__(self, app_id: str, app_secret: str, owner_id: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.owner_id = owner_id
        self.token = None
        self.token_expires_at = 0
        self.image_service = ImageService(owner_id)

    def get_access_token(self) -> str:
        """获取或刷新 Access Token"""
        if self.token and time.time() < self.token_expires_at:
            return self.token

        url = (
            f"https://api.weixin.qq.com/cgi-bin/token"
            f"?grant_type=client_credential"
            f"&appid={self.app_id}"
            f"&secret={self.app_secret}"
        )
        resp = requests.get(url)
        data = resp.json()

        if 'access_token' in data:
            self.token = data['access_token']
            # 提前 5 分钟过期
            self.token_expires_at = time.time() + data['expires_in'] - 300
            return self.token
        else:
            raise Exception(f"获取 Token 失败: {data}")

    async def upload_cover_image(self, image_path: Path) -> str:
        """
        上传封面图片（永久素材）

        Args:
            image_path: 本地图片路径

        Returns:
            media_id
        """
        token = self.get_access_token()
        url = (
            f"https://api.weixin.qq.com/cgi-bin/material/add_material"
            f"?access_token={token}&type=image"
        )

        # 读取并压缩图片
        with open(image_path, 'rb') as f:
            image_bytes = f.read()

        compressed = self.image_service.compress_image_stream(
            image_bytes,
            self.MAX_COVER_IMG_SIZE
        )

        files = {
            'media': (image_path.name, compressed, 'image/jpeg')
        }
        resp = requests.post(url, files=files)
        result = resp.json()

        if 'media_id' in result:
            return result['media_id']
        else:
            raise Exception(f"封面上传失败: {result}")

    async def upload_article_image(self, image_url: str) -> str:
        """
        上传正文图片（临时素材，返回 URL）

        Args:
            image_url: 图片 URL

        Returns:
            微信 CDN URL
        """
        token = self.get_access_token()
        url = (
            f"https://api.weixin.qq.com/cgi-bin/media/uploadimg"
            f"?access_token={token}"
        )

        # 下载并压缩（内存处理）
        compressed = await self.image_service.download_and_compress(
            image_url,
            self.MAX_ARTICLE_IMG_SIZE
        )

        files = {
            'media': (f'img_{uuid.uuid4().hex}.jpg', compressed, 'image/jpeg')
        }
        resp = requests.post(url, files=files)
        result = resp.json()

        if 'url' in result:
            return result['url']
        else:
            raise Exception(f"图片上传失败: {result}")

    async def process_html_images(self, html_content: str) -> str:
        """
        处理 HTML 中的图片（替换为微信 URL）

        Args:
            html_content: 原始 HTML

        Returns:
            处理后的 HTML
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        imgs = soup.find_all('img')

        for img in imgs:
            src = img.get('src')
            if not src:
                continue

            # 跳过已经是微信链接的图片
            if 'mmbiz.qpic.cn' in src:
                continue

            # 上传并替换
            try:
                wechat_url = await self.upload_article_image(src)
                img['src'] = wechat_url

                # 清理多余属性
                for attr in ['data-src', 'style', 'width', 'height']:
                    if img.get(attr):
                        del img[attr]
            except Exception as e:
                print(f"图片上传失败 {src}: {e}")
                # 保留原 URL，不中断流程

        return str(soup)

    async def submit_draft(self, article_data: dict) -> str:
        """
        提交草稿到微信公众号

        Args:
            article_data: 文章数据

        Returns:
            media_id
        """
        token = self.get_access_token()
        url = (
            f"https://api.weixin.qq.com/cgi-bin/draft/add"
            f"?access_token={token}"
        )

        payload = {"articles": [article_data]}

        resp = requests.post(
            url,
            json=payload,
            headers={'Content-Type': 'application/json; charset=utf-8'}
        )
        result = resp.json()

        if 'media_id' in result:
            return result['media_id']
        else:
            raise Exception(f"草稿提交失败: {result}")
```

#### 4.3 同步 API 端点
```python
# apis/ai.py

@router.post("/ai/drafts/{draft_id}/sync-wechat")
async def sync_draft_to_wechat(
    draft_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    同步本地草稿到微信公众号草稿箱

    流程：
    1. 检查微信授权配置
    2. 获取本地草稿
    3. 提取并下载封面图（即梦图片）
    4. 转换 Markdown → HTML
    5. 处理正文图片（上传微信）
    6. 提交草稿
    7. 更新本地草稿元数据
    """
    # 1. 检查授权
    if not current_user.wechat_app_id or not current_user.wechat_app_secret:
        raise HTTPException(
            status_code=400,
            detail="请先在个人中心配置微信公众号 App ID 和 Secret"
        )

    # 2. 获取草稿
    draft = get_local_draft(current_user.username, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")

    # 3. 初始化服务
    wechat_service = WeChatDraftService(
        app_id=current_user.wechat_app_id,
        app_secret=current_user.wechat_app_secret,
        owner_id=current_user.username
    )
    image_service = ImageService(current_user.username)

    # 4. 处理封面图
    cover_url = extract_first_image_url(draft['content'])
    if not cover_url:
        raise HTTPException(status_code=400, detail="草稿中未找到封面图片")

    # 如果是即梦图片，直接使用；否则下载
    if 'jimeng' in cover_url or cover_url.startswith('http'):
        cover_path = await image_service.download_jimeng_image(cover_url)
    else:
        raise HTTPException(status_code=400, detail="无效的封面图片 URL")

    # 5. 上传封面
    thumb_media_id = await wechat_service.upload_cover_image(cover_path)

    # 6. 转换 Markdown → HTML
    html_content = markdown_to_html(draft['content'])

    # 7. 处理正文图片
    clean_html = await wechat_service.process_html_images(html_content)

    # 8. 提交草稿
    article_payload = {
        "title": draft.get('title', '未命名'),
        "author": draft['metadata'].get('author', current_user.nickname or '作者'),
        "digest": draft['metadata'].get('digest', '')[:120],
        "content": clean_html,
        "content_source_url": "",
        "thumb_media_id": thumb_media_id,
        "need_open_comment": 1,
        "only_fans_can_comment": 0
    }

    media_id = await wechat_service.submit_draft(article_payload)

    # 9. 更新本地草稿元数据
    update_local_draft(current_user.username, draft_id, {
        'metadata': {
            **draft.get('metadata', {}),
            'wechat_media_id': media_id,
            'synced_at': datetime.now().isoformat()
        }
    })

    return {
        "success": True,
        "media_id": media_id,
        "message": "草稿已成功同步到微信公众号"
    }
```

---

### 5. 多用户隔离机制

**隔离点清单：**

| 资源类型 | 隔离方式 | 实现位置 |
|---------|---------|---------|
| 本地草稿 | `{owner_id}.jsonl` | `core/ai_service.py` |
| 即梦图片 | `imgs/{owner_id}/` | `core/image_service.py` |
| 微信授权 | `user.wechat_app_id/secret` | `core/models/user.py` |
| AI 配置 | `ai_profiles.owner_id` 索引 | `core/models/ai_profile.py` |
| 创作记录 | `ai_compose_result.owner_id` 索引 | `core/models/ai_compose_result.py` |
| 日额度 | `ai_daily_usage.owner_id` 索引 | `core/models/ai_daily_usage.py` |

**验证点：**
- ✅ 用户 A 无法访问用户 B 的草稿
- ✅ 用户 A 的图片存储在独立目录
- ✅ 用户 A 的微信授权只用于自己的同步
- ✅ 数据库查询都带 `owner_id` 过滤

---

## Open Questions

### 1. Markdown 排版优化

**问题：** pipeline.py 使用 `md2wechat.com` 进行 Markdown 排版（Playwright 自动化），是否保留？

**选项：**
- (a) 保留 - 排版效果好，但依赖外部服务和 Playwright
- (b) 替换为本地 CSS - 自己实现微信风格 CSS，不依赖外部服务
- (c) 可选功能 - 用户在草稿页面勾选"使用高级排版"

**建议：** 先实现 (b) 本地 CSS 排版，后续可以添加 (c) 作为可选增强。

---

### 2. 同步失败重试机制

**问题：** 如果同步微信失败（网络问题、Token 过期等），如何处理？

**当前系统已有：**
- `AIPublishTask` 表支持重试队列
- `process_publish_task()` 函数处理重试逻辑

**建议：** 复用现有重试队列机制，同步失败时自动进入队列。

---

### 3. 即梦图片的版权和水印

**问题：** 即梦生成的图片是否需要添加水印或版权声明？

**建议：** 在草稿编辑页面提供"添加水印"选项，用户可选择是否在图片上叠加自定义水印。

---

## Implementation Checklist

### Phase 1: 按钮状态切换（前端优化）✨ 优先级：高 | 风险：低 | 预计工期：1 天

- [ ] 修改 `apis/ai.py` - 草稿列表接口增加过滤参数
  - [ ] 添加 `article_id` 过滤
  - [ ] 添加 `mode` 过滤
  - [ ] 更新接口文档

- [ ] 修改 `web_ui/src/views/AiStudio.vue`
  - [ ] 添加 `loadDraftStatus()` 函数
  - [ ] 添加 `getButtonConfig()` 函数
  - [ ] 动态渲染按钮（创作/查看）
  - [ ] 处理"查看"按钮点击（跳转草稿页）

- [ ] 新建或修改草稿编辑页面 `web_ui/src/views/DraftEditor.vue`
  - [ ] 添加"重新生成"按钮
  - [ ] 实现 `regenerate()` 函数（调用 force_refresh）
  - [ ] 添加"同步到公众号"按钮（占位，Phase 3 实现）

- [ ] 测试
  - [ ] 无草稿时显示"一键创作"
  - [ ] 有草稿时显示"查看草稿"
  - [ ] 点击"查看"正确跳转
  - [ ] 重新生成功能正常

---

### Phase 2: 提示词优化（内容改造）✨ 优先级：中 | 风险：低 | 预计工期：2 天

- [ ] 新建 `core/prompt_templates.py` 模块
  - [ ] 定义 `PromptStyle` 枚举
  - [ ] 实现 `build_natural_prompt()` 函数
  - [ ] 添加平台特定的提示词变体（微信/小红书/知乎）
  - [ ] 添加案例库（few-shot examples）

- [ ] 修改 `core/ai_service.py`
  - [ ] 重构 `build_prompt()` 函数
  - [ ] 集成 `prompt_templates.build_natural_prompt()`
  - [ ] 保留原有逻辑作为 fallback

- [ ] 前端文案优化 `web_ui/src/views/AiStudio.vue`
  - [ ] 修改创作设置面板的文案
  - [ ] 修改写作风格的描述（去列表化）
  - [ ] 修改篇幅选项的说明
  - [ ] 修改平台选项的提示

- [ ] 前端文案优化 `web_ui/src/api/ai.ts`
  - [ ] 更新接口注释和 TypeScript 类型
  - [ ] 添加字段说明（去技术术语）

- [ ] 测试与调优
  - [ ] 对比生成效果（优化前 vs 优化后）
  - [ ] A/B 测试不同提示词风格
  - [ ] 收集用户反馈

---

### Phase 3: 公众号同步功能（核心功能）✨ 优先级：高 | 风险：中 | 预计工期：3 天

#### 3.1 基础服务层

- [ ] 新建 `core/image_service.py`
  - [ ] 实现 `ImageService` 类
  - [ ] `download_jimeng_image()` - 下载即梦图片
  - [ ] `compress_image_stream()` - 内存压缩
  - [ ] `download_and_compress()` - 下载外链并压缩
  - [ ] 添加单元测试

- [ ] 新建 `core/wechat_draft_service.py`
  - [ ] 实现 `WeChatDraftService` 类
  - [ ] `get_access_token()` - Token 管理
  - [ ] `upload_cover_image()` - 上传封面
  - [ ] `upload_article_image()` - 上传正文图片
  - [ ] `process_html_images()` - 批量处理图片
  - [ ] `submit_draft()` - 提交草稿
  - [ ] 添加单元测试

- [ ] 修改 `core/ai_service.py`
  - [ ] 添加辅助函数 `extract_first_image_url()`
  - [ ] 添加辅助函数 `markdown_to_html()`
  - [ ] 更新 `save_local_draft()` - 记录图片 URL

#### 3.2 API 端点

- [ ] 修改 `apis/ai.py`
  - [ ] 实现 `POST /ai/drafts/{draft_id}/sync-wechat`
  - [ ] 添加请求参数验证
  - [ ] 添加错误处理和重试逻辑
  - [ ] 集成 `WeChatDraftService`

- [ ] 修改 `apis/user.py` (如果需要)
  - [ ] 添加微信授权配置接口
  - [ ] 添加授权状态检查接口

#### 3.3 前端集成

- [ ] 修改 `web_ui/src/api/ai.ts`
  - [ ] 添加 `syncDraftToWechat()` 函数
  - [ ] 添加类型定义

- [ ] 修改 `web_ui/src/views/DraftEditor.vue`
  - [ ] 实现"同步到公众号"按钮逻辑
  - [ ] 添加同步进度提示
  - [ ] 添加同步结果反馈（成功/失败）
  - [ ] 显示 media_id（如果成功）

- [ ] 修改 `web_ui/src/views/EditUser.vue`
  - [ ] 添加微信授权配置表单
  - [ ] 添加 `wechat_app_id` 输入框
  - [ ] 添加 `wechat_app_secret` 输入框（密码框）
  - [ ] 添加授权状态提示

#### 3.4 数据库迁移

- [ ] 检查 `users` 表是否已有字段
  - [ ] `wechat_app_id`
  - [ ] `wechat_app_secret`
  - [ ] 如果没有，创建迁移脚本

- [ ] 更新本地草稿 metadata 结构
  - [ ] 添加 `wechat_media_id` 字段
  - [ ] 添加 `synced_at` 时间戳

#### 3.5 测试

- [ ] 单元测试
  - [ ] 测试图片下载和压缩
  - [ ] 测试微信 API 调用（Mock）
  - [ ] 测试多用户隔离

- [ ] 集成测试
  - [ ] 端到端同步流程测试
  - [ ] 错误场景测试（网络失败、Token 过期等）
  - [ ] 多用户并发测试

- [ ] 用户验收测试
  - [ ] 真实公众号同步测试
  - [ ] 图片显示效果验证
  - [ ] 草稿箱状态验证

---

## Next Steps

执行顺序建议：

1. **Phase 1 (1 天)** - 按钮状态切换
   - 快速见效，提升用户体验
   - 为 Phase 3 的草稿页面打基础

2. **Phase 2 (2 天)** - 提示词优化
   - 独立模块，不影响其他功能
   - 可以与 Phase 3 并行开发

3. **Phase 3 (3 天)** - 公众号同步
   - 核心功能，需要充分测试
   - 依赖 Phase 1 的草稿页面

**总预计工期：** 6 个工作日

**风险控制：**
- 每个 Phase 独立可测试
- Phase 1 和 Phase 2 可以先上线
- Phase 3 可以分批发布（先内测，再全量）

---

## Technical Debt & Future Enhancements

### 技术债务

1. **pipeline.py 的 Playwright 依赖**
   - 当前方案：暂不集成 md2wechat.com 排版
   - 后续优化：实现本地 CSS 排版或集成为可选功能

2. **图片存储空间管理**
   - 当前方案：即梦图片不自动清理
   - 后续优化：添加管理后台，支持手动或定时清理

3. **同步性能优化**
   - 当前方案：串行处理图片上传
   - 后续优化：并行上传多张图片，提升速度

### 未来增强

1. **批量同步** - 支持一键同步多篇草稿
2. **定时发布** - 设置发布时间，自动同步
3. **草稿历史** - 记录每次同步的版本，支持回滚
4. **图片水印** - 自动添加自定义水印
5. **其他平台支持** - 小红书、知乎等平台的草稿同步

---

## References

- `pipeline.py` - 微信草稿发布脚本（图片处理逻辑参考）
- `core/ai_service.py` - AI 创作核心服务
- `web_ui/src/views/AiStudio.vue` - 创作中台前端
- 微信公众号开发文档 - https://developers.weixin.qq.com/doc/offiaccount/
