# Content Studio（商业化微信公众号内容创作平台）

Content Studio 是一个面向自媒体与内容团队的微信公众号内容平台，提供从订阅监控、文章抓取到 AI 分析/创作/仿写的一体化流程。

## 核心能力

- 手机号 + 密码注册/登录
- 多用户数据隔离（公众号、文章、标签、任务、AI 配置均按用户隔离）
- OpenAI 兼容接口配置（`base_url` + `api_key` + `model`）
- 每篇文章一键 `分析` / `创作` / `仿写`
- 创作中台总览（公众号数、文章数、草稿数、套餐配额）
- 免费 / 付费 / 高级 三档能力分层（AI 配额、图片配额、草稿投递权限）
- 本地草稿箱 + 公众号草稿箱投递（扫码授权后可一键尝试同步）
- 草稿投递队列（失败自动入队、手动重试、批量处理）
- 管理员套餐后台（用户套餐调整、配额重置）
- 订阅管理、消息任务、标签管理、配置管理
- Docker 容器化部署，支持 PostgreSQL

## 快速启动

### 方式一：本地启动

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml
python init_sys.py
python main.py -job True -init False
```

访问：`http://127.0.0.1:8001`

### 方式二：Docker + PostgreSQL（推荐）

```bash
cd compose
docker compose -f docker-compose-postgresql.yaml up -d --build
```

默认访问：`http://127.0.0.1:8001`

默认管理员：
- 用户名：`admin`
- 密码：`admin@123`

## 关键配置

`config.yaml` 中重点配置：

- `db`: 数据库连接串（推荐 PostgreSQL）
- `secret`: JWT 签名密钥
- `server.web_name`: 前端标题
- `token_expire_minutes`: 登录有效期
- `rss.*`: RSS 输出行为

PostgreSQL 连接示例：

```text
postgresql://rss_user:pass123456@postgres:5432/we_mp_rss
```

## AI 创作配置

登录后进入 `AI 创作` 页面，填写：

- `Base URL`（如 OpenAI 兼容网关地址）
- `Model`（如 `kimi-k2.5`）
- `API Key`

保存后可在文章列表对单篇内容执行：
- 分析
- 创作
- 仿写

创作完成后支持：
- 一键保存本地草稿箱
- 一键尝试发布公众号草稿箱（需先扫码授权，且套餐支持）
- 即梦图片生成（未配置 AK/SK 时自动降级为提示词）


## 使用文档

- 启动与使用指南：`docs/guides/启动与使用指南.md`
- 清理历史文件脚本：`script/clean_history.sh`

## 商业化交付说明

本版本已完成：

- 统一 UI 导航与布局
- 手机号注册登录
- 多租户数据隔离
- AI 工作台及单篇文章一键创作能力
- PostgreSQL 容器化部署支持
- Playwright 端到端回归测试
