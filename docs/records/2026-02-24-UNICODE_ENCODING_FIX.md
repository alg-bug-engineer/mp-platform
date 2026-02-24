# Unicode 编码问题修复（草稿箱乱码）

## 问题描述

用户报告草稿箱显示的内容全是 Unicode 转义序列，例如：
```
\u63ed\u79d8GLM-5\u6280\u672f
```

而不是正常的中文：
```
揭秘GLM-5技术
```

## 根本原因

在多个关键位置使用了 Python `requests` 库的 `json=` 参数，该参数默认使用 `json.dumps()` 且 **默认 `ensure_ascii=True`**，导致：

1. **微信草稿箱同步** - 中文被转义后发送到微信 API
2. **AI 模型调用** - 提示词中的中文被转义
3. **FastAPI 响应** - API 响应中的中文被转义

### 技术细节

```python
# ❌ 错误的方式（默认 ensure_ascii=True）
requests.post(url, json={"title": "中文标题"})
# 发送: {"title": "\u4e2d\u6587\u6807\u9898"}

# ✅ 正确的方式（ensure_ascii=False）
payload_json = json.dumps({"title": "中文标题"}, ensure_ascii=False)
requests.post(url, data=payload_json.encode('utf-8'), headers={'Content-Type': 'application/json; charset=utf-8'})
# 发送: {"title": "中文标题"}
```

## 修复方案

### 1. FastAPI 应用级别配置 (web.py)

**文件**: `web.py`

添加自定义 `UnicodeJSONResponse` 类：

```python
class UnicodeJSONResponse(JSONResponse):
    """自定义 JSON 响应类，确保中文不被转义"""
    def render(self, content: Any) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,  # 关键：不转义非ASCII字符
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")


app = FastAPI(
    # ...
    default_response_class=UnicodeJSONResponse,  # 使用自定义响应类
)
```

**影响**：所有 FastAPI API 端点的响应都使用正确的中文编码

### 2. 微信草稿箱同步修复 (core/ai_service.py)

**文件**: `core/ai_service.py:2564-2571`

**修改前**：
```python
endpoint = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}"
try:
    resp = requests.post(
        endpoint,
        json={"articles": articles},  # ❌ 默认转义中文
        headers={"Content-Type": "application/json"},
        timeout=(5, 40),
    )
```

**修改后**：
```python
endpoint = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}"
try:
    # 显式序列化 JSON，确保中文不被转义为 \uXXXX（修复草稿箱乱码问题）
    payload_json = json.dumps({"articles": articles}, ensure_ascii=False)
    resp = requests.post(
        endpoint,
        data=payload_json.encode('utf-8'),  # ✅ 使用 UTF-8 编码
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=(5, 40),
    )
```

**影响**：发送到微信草稿箱的内容现在是正常中文，不再是转义序列

### 3. AI 模型调用修复 (core/ai_service.py)

**文件**: `core/ai_service.py:751-760`

**修改前**：
```python
payload = {
    "model": model_name,
    "temperature": float(temperature) / 100.0,
    "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ],
}
try:
    resp = requests.post(endpoint, json=payload, headers=headers, timeout=180)  # ❌
```

**修改后**：
```python
payload = {
    "model": model_name,
    "temperature": float(temperature) / 100.0,
    "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ],
}
try:
    # 显式序列化 JSON，确保中文不被转义
    payload_json = json.dumps(payload, ensure_ascii=False)
    resp = requests.post(endpoint, data=payload_json.encode('utf-8'),
                        headers={**headers, 'Content-Type': 'application/json; charset=utf-8'},
                        timeout=180)  # ✅
```

**影响**：发送到 AI 模型的提示词现在是正常中文

## 测试验证

### 1. 单元测试

运行测试脚本：
```bash
python tests/manual/test_unicode_response.py
```

**预期结果**：
```
✅ 解析成功!
   标题: 揭秘GLM-5技术
   作者: AI 助手
   摘要: 深度解析 AI 技术
```

### 2. 集成测试

1. **启动服务**：
   ```bash
   # 停止现有服务
   pkill -f "python main.py"

   # 重新启动
   python main.py -job True -init True
   ```

2. **测试草稿创建**：
   - 登录系统
   - 创建包含中文的草稿
   - 检查草稿列表 API 响应

3. **测试微信同步**：
   - 创建草稿
   - 同步到微信草稿箱
   - 在微信公众号后台查看草稿

**预期结果**：
- ✅ 草稿列表显示正常中文
- ✅ 微信草稿箱显示正常中文
- ❌ 不应再出现 `\u63ed\u79d8` 等转义序列

### 3. API 测试

```bash
# 测试草稿列表 API
curl -H "Authorization: Bearer YOUR_TOKEN" \
     http://localhost:8001/api/v1/wx/ai/drafts?limit=1
```

**预期响应**（部分）：
```json
{
  "code": 0,
  "message": "success",
  "data": [
    {
      "title": "揭秘GLM-5技术",  // ✅ 正常中文，不是 \uXXXX
      "content": "这是一篇关于 AI 的文章..."
    }
  ]
}
```

## 对比：修复前后

| 方面 | 修复前 | 修复后 |
|------|--------|--------|
| **草稿列表 API** | `{"title": "\u63ed\u79d8"}` | `{"title": "揭秘"}` |
| **微信草稿箱** | 显示 `\u63ed\u79d8GLM-5\u6280\u672f` | 显示 `揭秘GLM-5技术` |
| **AI 提示词** | 中文被转义发送到模型 | 正常中文发送到模型 |
| **响应大小** | 更大（转义序列更长） | 更小（UTF-8 编码） |
| **可读性** | ❌ 无法阅读 | ✅ 正常阅读 |

### 示例对比

**修复前（错误）**：
```
\u63ed\u79d8GLM-5\u6280\u672f\u5e95\u724c
```

**修复后（正确）**：
```
揭秘GLM-5技术底牌
```

## 影响范围

修改的文件：
1. ✅ `web.py` - FastAPI 应用配置
2. ✅ `core/ai_service.py` - 两处 `requests.post()` 调用

影响的功能：
1. ✅ 所有 API 响应
2. ✅ 微信草稿箱同步
3. ✅ AI 模型调用
4. ✅ 草稿列表显示

## 技术说明

### 为什么 `ensure_ascii=True` 是默认值？

Python 的 `json.dumps()` 默认 `ensure_ascii=True` 是为了：
1. 确保 JSON 只包含 ASCII 字符
2. 避免编码问题（所有非 ASCII 字符都转义）
3. 兼容性更好（某些老系统不支持 UTF-8）

### 为什么我们要用 `ensure_ascii=False`？

1. **现代 Web 标准** - UTF-8 已经是事实标准
2. **可读性** - 中文字符直接显示，便于调试
3. **传输效率** - UTF-8 编码的中文比转义序列更小
4. **微信 API 要求** - 微信 API 正确处理 UTF-8 编码

### 编码流程

```
原始字符串: "揭秘GLM-5技术"
    ↓
ensure_ascii=True (错误):
    json.dumps() → "\u63ed\u79d8GLM-5\u6280\u672f"
    encode('utf-8') → b'\\u63ed\\u79d8...' (转义序列的字节)
    微信显示 → \u63ed\u79d8... (乱码)

ensure_ascii=False (正确):
    json.dumps() → "揭秘GLM-5技术"
    encode('utf-8') → b'\xe6\x8f\xad...' (UTF-8 字节)
    微信显示 → 揭秘GLM-5技术 (正常)
```

## 常见问题

### Q1: 为什么有些地方已经用了 `ensure_ascii=False` 但还是乱码？

**A**: 问题出在 `requests.post()` 的 `json=` 参数，它会忽略你之前的 `ensure_ascii=False` 设置。

```python
# ❌ 这样不行
data = json.dumps(payload, ensure_ascii=False)
requests.post(url, json=data)  # json= 会重新序列化，使用默认的 ensure_ascii=True

# ✅ 这样才对
data_json = json.dumps(payload, ensure_ascii=False)
requests.post(url, data=data_json.encode('utf-8'), headers={'Content-Type': 'application/json; charset=utf-8'})
```

### Q2: 本地文件保存是正常的，为什么 API 返回还是乱码？

**A**: 本地文件保存使用了 `ensure_ascii=False`（正确），但 FastAPI 默认响应使用的是 `ensure_ascii=True`（错误）。需要配置 `default_response_class`。

### Q3: 修复后会影响已有的草稿吗？

**A**: 不会。已保存的草稿文件中的数据是正常的（因为保存时已经用了 `ensure_ascii=False`）。修复只影响：
- API 响应的显示
- 新创建的草稿同步到微信

### Q4: 如果还有其他地方出现乱码怎么办？

**A**: 搜索所有使用 `requests.post()` 的地方：

```bash
grep -rn "requests.post" --include="*.py" | grep "json="
```

然后逐个修复，使用 `data=json.dumps(..., ensure_ascii=False).encode('utf-8')`。

## 验证修复

### 步骤 1: 重启服务

```bash
# 停止
pkill -f "python main.py"

# 启动
python main.py -job True -init True
```

### 步骤 2: 测试草稿列表

访问草稿列表 API，检查返回的 JSON：
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
     http://localhost:8001/api/v1/wx/ai/drafts?limit=1 | python -m json.tool
```

应该看到正常的中文字符，而不是 `\uXXXX` 转义序列。

### 步骤 3: 测试微信同步

1. 创建一个新草稿（包含中文标题和内容）
2. 同步到微信草稿箱
3. 在微信公众号后台查看草稿

应该看到正常的中文，而不是乱码。

## 总结

**修复内容**：
1. ✅ FastAPI 应用级别使用 `UnicodeJSONResponse`
2. ✅ 微信草稿箱同步使用 `ensure_ascii=False`
3. ✅ AI 模型调用使用 `ensure_ascii=False`

**预期效果**：
- 所有 API 响应显示正常中文
- 微信草稿箱显示正常中文
- AI 模型接收正常中文提示词

**部署建议**：
- 已测试通过，可直接部署到生产环境
- 修复后的代码向后兼容，不影响已有数据

---

**修复完成时间**: 2026-02-24
**测试状态**: ✅ 全部通过
**部署状态**: 可直接部署
