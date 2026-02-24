# Content Studio 完整项目手册

本文档面向产品、研发、测试、运维与运营角色，覆盖项目的功能全景、环境配置、启动停止、构建发布、订阅付费、日常操作与故障排查。

## 1. 项目定位

- 项目名称：`Content Studio`（基于 `we-mp-rss` 演进）
- 目标：打造自媒体创作者的一站式工作台，覆盖“选题 -> 创作 -> 配图 -> 草稿 -> 发布 -> 复盘”
- 核心价值：
  - 多用户数据隔离
  - AI 创作与平台适配
  - 套餐化能力分层与付费闭环
  - 可部署、可运营、可持续迭代

## 2. 功能总览

### 2.1 创作者侧

- 账号体系：
  - 手机号注册 / 登录
  - 个人中心 / 修改密码
- 内容工作台：
  - 内容池（公众号文章列表）
  - 订阅管理（公众号订阅/检索）
  - AI 创作中台（分析、创作、仿写）
  - 本地草稿箱与公众号草稿队列
- 运营工具：
  - 消息任务
  - 标签管理
  - 系统配置
- 商业化：
  - 套餐中心（下单、支付、订单状态）

### 2.2 管理员侧

- 套餐管理（档位、配额、策略）
- 全局订单视图
- 到期扫描与降级
- 系统级配置与监控

## 3. 技术架构概览

- 后端：Python + FastAPI（路由位于 `apis/`）
- 前端：Vue 3 + Vite + Arco Design（位于 `web_ui/`）
- 数据库：SQLite（默认）/ PostgreSQL（推荐生产）
- 定时任务：`jobs/`
- 静态产物：`static/`

关键目录：

- `apis/`：API 接口（认证、AI、计费、订阅等）
- `core/`：领域服务（AI、套餐、计费、授权、数据库）
- `web_ui/`：前端源码
- `static/`：前端构建输出与运行时静态资源
- `tests/`：测试与联调脚本
- `docs/`：文档
- `compose/`：Docker 编排

## 4. 环境要求

- Python：`3.10+`
- Node.js：`18+`
- npm：`8+`
- Docker / Docker Compose：容器部署必需

## 5. 配置说明

配置文件：

- 模板：`config.example.yaml`
- 生效配置：`config.yaml`

关键配置域（示例）：

- `db.*`：数据库连接
- `auth.*`：认证与会话
- `ai.*`：模型配置、本地规则、草稿目录、即梦参数
- `billing.*`：订单与订阅策略
- `server.*`：端口与服务行为

敏感信息建议使用环境变量注入，避免明文入库：

- `OPENAI_API_KEY` / 等价模型 Key
- `JIMENG_AK`
- `JIMENG_SK`
- 生产数据库账号密码

## 6. 启停手册

### 6.1 本地开发启动

```bash
cd /Users/zhangqilai/project/we-mp-rss
python3.10 -m pip install -r requirements.txt
cd web_ui && npm install && cd ..
cp config.example.yaml config.yaml
python3.10 init_sys.py
cd web_ui && npm run build && cd ..
rsync -a --delete web_ui/dist/ static/
python3.10 main.py -job True -init False
```

访问：

- `http://127.0.0.1:8001`

停止：

- 前台进程：`Ctrl+C`
- 后台进程：`pkill -f "python3.10 main.py"`

### 6.2 Docker 启动（推荐）

```bash
cd /Users/zhangqilai/project/we-mp-rss/compose
docker compose -f docker-compose-postgresql.yaml up -d --build
```

停止：

```bash
docker compose -f docker-compose-postgresql.yaml down
```

查看状态：

```bash
docker compose -f docker-compose-postgresql.yaml ps
docker compose -f docker-compose-postgresql.yaml logs -f
```

## 7. 构建与发布

### 7.1 前端构建

```bash
cd /Users/zhangqilai/project/we-mp-rss/web_ui
npm run build
cd ..
rsync -a --delete web_ui/dist/ static/
```

### 7.2 静态资源清理

```bash
./script/clean_history.sh
```

## 8. 业务操作手册

### 8.1 创作者首日流程

1. 注册并登录
2. 进入“创作”页填写 AI 配置（Base URL / Model / API Key）
3. 在“订阅”中确认公众号内容来源
4. 在“创作中台”对文章执行分析/创作/仿写
5. 选择是否生图（即梦）
6. 结果发布到本地草稿箱，按需同步公众号
7. 同步失败时在“投递队列”重试

### 8.2 运营分组导航

- 主入口：`/workspace/ops`
- 子模块：
  - `/workspace/ops/messages`
  - `/workspace/ops/tags`
  - `/workspace/ops/configs`

### 8.3 深链能力

- 创作结果：`/workspace/studio?article_id=xxx&mode=create`
- 草稿定位：`/workspace/draftbox?section=drafts&draft_id=xxx`
- 订单定位：`/workspace/billing?order_no=xxx`

## 9. 订阅与付费机制

### 9.1 套餐模型

- `free`：基础能力，低配额
- `pro`：更高配额，开放更多创作能力
- `premium`：高阶能力与更高额度

### 9.2 订单流转

1. 用户创建订单（`pending`）
2. 支付确认（mock 或真实网关）
3. 订阅生效并更新配额 / 到期时间
4. 到期扫描任务执行降级

### 9.3 管理端动作

- 查看全局订单
- 执行到期扫描
- 调整用户档位与配额

## 10. AI 与即梦能力

### 10.1 AI 创作配置

- 配置入口：创作中台 `AI 创作配置`
- 支持 OpenAI 兼容协议模型

### 10.2 即梦生图

- 参数：`JIMENG_AK` / `JIMENG_SK`
- 请求 key 支持回退（如 v40 -> v30）
- 未配置或失败时可降级为“配图提示词”

联调脚本：

```bash
export JIMENG_AK='your-ak'
export JIMENG_SK='your-sk'
python tests/test_jimeng_api.py --scene article_cover --topic "自媒体增长" --style "极简商业"
```

## 11. 测试与质量保障

测试目录已统一为 `tests/`。

推荐执行：

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

## 12. 运维建议

### 12.1 生产建议

- 优先 PostgreSQL
- 所有密钥走环境变量或密钥管理服务
- 对关键接口开启访问日志与告警
- 定期备份数据库与草稿数据目录

### 12.2 监控项建议

- 接口成功率 / 错误率
- AI 请求失败率
- 生图成功率
- 草稿投递成功率
- 订单支付成功率 / 过期降级执行数

## 13. 常见问题

### 13.1 页面样式异常

- 先执行前端构建并同步 `static/`
- 清理浏览器缓存后重试

### 13.2 登录后被重定向

- 未登录访问受限路由会跳登录页
- 权限不足访问管理员路由会回退到可访问页面

### 13.3 公众号投递失败

- 检查是否已扫码授权
- 检查套餐是否支持公众号草稿投递
- 在投递队列中执行重试

## 14. 迭代建议

- 接入真实支付网关与回调验签
- 增强团队协作（多角色、多账号）
- 增加发布效果回流与自动复盘
- 打通运营指标看板

