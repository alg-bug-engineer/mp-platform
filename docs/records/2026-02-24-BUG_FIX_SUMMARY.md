# Bug Fix: "[object Object]" Error in AI Generation

## 问题描述 (Problem Description)

用户报告：
- 不论是分析还是创作，生成结果时都会出现 `error [object Object]` 错误
- 草稿箱没有结果
- 但运营指标中的稿件数量一直增加

User reported:
- "[object Object]" error appears during AI generation (analyze/create/rewrite)
- No drafts appear in the draft box
- But draft count in metrics keeps increasing

## 根本原因 (Root Cause)

### 0. 参数验证失败 (Parameter Validation Failure) ⚠️ **主要问题**

**文件**: `web_ui/src/views/AiStudio.vue:562` + `apis/ai.py:364`

前端请求的 `limit` 参数超过后端限制：

```typescript
// ❌ 前端请求 1000
const DRAFT_LOOKUP_LIMIT = 1000
```

```python
# ❌ 后端最大限制 200
limit: int = Query(20, ge=1, le=200)
```

当前端请求 `GET /api/v1/wx/ai/drafts?limit=1000` 时，FastAPI 验证器拒绝请求，返回 `422 Unprocessable Entity`。这个验证错误的格式与普通错误不同，导致前端无法正确解析，显示 "[object Object]"。

### 1. 前端错误处理问题 (Frontend Error Handling Issue)

**文件**: `web_ui/src/api/http.ts`

当后端返回错误响应时，HTTP 拦截器直接将整个响应对象(object)传递给错误处理函数：

```typescript
// ❌ 错误的方式 (Before)
return Promise.reject(response.data)  // response.data 是一个对象
```

前端错误处理函数 `handleActionableError` 使用 `String(error)` 将错误转换为字符串，导致显示 "[object Object]"：

```typescript
// ❌ 错误的方式 (Before)
const msg = String(error || '操作失败')  // 对象转字符串 = "[object Object]"
```

### 2. 潜在的后端序列化问题 (Potential Backend Serialization Issue)

**文件**: `apis/ai.py`

`_serialize_plan` 函数在序列化 datetime 字段时缺少错误处理，如果 datetime 对象格式不正确可能导致异常：

```python
# ❌ 缺少错误处理 (Before)
data["quota_reset_at"] = reset_at.isoformat() if reset_at else None
```

## 修复方案 (Solution)

### 0. 修复参数不匹配 (Fix Parameter Mismatch) ⭐ **关键修复**

**文件**: `web_ui/src/views/AiStudio.vue` (Line 562)

```typescript
// ✅ 修复后 (After)
const DRAFT_LOOKUP_LIMIT = 200  // 匹配后端 API 最大限制 (le=200)
```

**改进说明**:
- 将前端的 `DRAFT_LOOKUP_LIMIT` 从 1000 降低到 200
- 匹配后端 API 的最大限制
- 避免 422 参数验证错误

### 1. 增强 HTTP 拦截器处理 422 错误 (Handle 422 Validation Errors)

**文件**: `web_ui/src/api/http.ts` (Error Interceptor)

```typescript
// ✅ 修复后 (After)
// 处理 FastAPI 422 验证错误
if (error?.response?.status === 422) {
  const detail = error?.response?.data?.detail
  if (Array.isArray(detail) && detail.length > 0) {
    // FastAPI 验证错误格式: [{loc: [...], msg: "...", type: "..."}]
    errorMsg = detail.map((err: any) => err.msg || err.type).join('; ')
  } else {
    errorMsg = '请求参数验证失败'
  }
}
```

**改进说明**:
- 专门处理 FastAPI 422 验证错误格式
- 提取并组合所有验证错误消息
- 提供清晰的参数验证失败提示

### 2. 修复 HTTP 拦截器通用错误 (Fix HTTP Interceptor General Errors)

**文件**: `web_ui/src/api/http.ts` (Line 58)

```typescript
// ✅ 修复后 (After)
// Reject with string message instead of object to avoid "[object Object]" error
return Promise.reject(errorMsg)
```

**改进说明**:
- 现在拦截器会拒绝(reject)一个字符串错误消息，而不是整个对象
- 这样用户可以看到实际的错误信息，而不是 "[object Object]"

### 3. 改进前端错误处理 (Improve Frontend Error Handler)

**文件**: `web_ui/src/views/AiStudio.vue` (Line 872-875)

```typescript
// ✅ 修复后 (After)
const handleActionableError = (error: any) => {
  // Extract error message from various error formats
  const msg = error instanceof Error
    ? error.message
    : String(error?.message || error?.response?.data?.message || error || '操作失败')
```

**改进说明**:
- 智能提取错误消息，支持多种错误格式
- 优先使用 `error.message` 属性
- 回退到 `error?.response?.data?.message`
- 最后才转换为字符串

### 4. 加固后端序列化 (Harden Backend Serialization)

**文件**: `apis/ai.py` (Line 107-120)

```python
# ✅ 修复后 (After)
def _serialize_plan(plan: dict) -> dict:
    data = dict(plan or {})
    reset_at = data.get("quota_reset_at")
    expire_at = data.get("plan_expires_at")
    # Safely serialize datetime fields
    try:
        data["quota_reset_at"] = reset_at.isoformat() if reset_at and hasattr(reset_at, 'isoformat') else None
    except Exception:
        data["quota_reset_at"] = None
    try:
        data["plan_expires_at"] = expire_at.isoformat() if expire_at and hasattr(expire_at, 'isoformat') else None
    except Exception:
        data["plan_expires_at"] = None
    return data
```

**改进说明**:
- 增加 `hasattr` 检查确保对象有 `isoformat` 方法
- 使用 try-except 捕获任何序列化异常
- 出错时安全地回退到 `None`

## 测试步骤 (Testing Steps)

### 1. 测试错误消息显示 (Test Error Message Display)

1. 启动后端：`python main.py -job True -init True`
2. 启动前端：`cd web_ui && npm run dev`
3. 登录系统，进入"创作中台"
4. 尝试进行以下操作：
   - 点击"一键分析"
   - 点击"一键创作"
   - 点击"一键仿写"
5. **预期结果**：
   - 如果有错误，应显示具体的错误消息（例如："平台 AI 服务未配置"）
   - 不应再显示 "[object Object]"
   - 浏览器控制台应显示详细错误信息

### 2. 测试草稿保存 (Test Draft Saving)

1. 成功生成内容后，检查：
   - 草稿箱中应显示新创建的草稿
   - 运营指标中的稿件数量应增加
   - 草稿详情应包含完整内容
2. 刷新页面后：
   - 草稿应仍然存在
   - 按钮状态应从"创作"变为"查看草稿"

### 3. 检查日志 (Check Logs)

后端日志应显示：
```
# 成功的情况
INFO: POST /api/v1/wx/ai/articles/{id}/create - 200 OK

# 失败的情况（现在应该有清晰的错误消息）
ERROR: 模型调用失败: ...
```

前端控制台应显示：
- API 响应的完整错误消息
- 不应有 "[object Object]" 字符串

## 可能的后续问题 (Potential Follow-up Issues)

### 如果草稿仍然不显示 (If Drafts Still Don't Appear):

1. **检查草稿文件路径**：
   ```bash
   # 查看草稿存储位置
   ls -la ./data/ai_drafts/

   # 查看用户草稿文件
   cat ./data/ai_drafts/{username}.jsonl
   ```

2. **检查文件权限**：
   ```bash
   # 确保应用有读写权限
   chmod -R 755 ./data/ai_drafts/
   ```

3. **检查用户 ID 一致性**：
   - 确认创建草稿时使用的 `owner_id` 与读取时一致
   - 检查 JWT token 中的用户信息

### 如果错误仍然不清晰 (If Error Messages Are Still Unclear):

1. 打开浏览器开发者工具 (F12)
2. 查看 Network 标签页
3. 找到失败的 API 请求
4. 查看 Response 内容，应该包含：
   ```json
   {
     "code": 非0值,
     "message": "具体错误信息",
     "data": null
   }
   ```

## 验证修复 (Verification)

运行自动验证脚本：

```bash
python tests/manual/verify_optimization.py
```

**预期输出**：
```
✅ 所有模块验证通过！
```

## 相关文件 (Related Files)

修改的文件：
- `web_ui/src/api/http.ts` - HTTP 拦截器
- `web_ui/src/views/AiStudio.vue` - 错误处理函数
- `apis/ai.py` - 序列化函数

相关的核心文件：
- `core/ai_service.py` - AI 服务和草稿管理
- `core/plan_service.py` - 用户套餐管理
- `web_ui/src/api/ai.ts` - API 类型定义

## 总结 (Summary)

本次修复解决了四个主要问题：

1. **⭐ 参数验证问题**：修复前后端 `limit` 参数不匹配（1000 vs 200）
2. **422 错误处理**：专门处理 FastAPI 验证错误格式
3. **用户体验改进**：错误消息现在清晰可读，不再显示 "[object Object]"
4. **后端稳定性**：datetime 序列化增加了错误处理，防止崩溃

**下一步**：
- 用户测试并提供反馈
- 如果仍有问题，查看具体的错误消息（现在应该清晰可见）
- 根据错误消息定位具体问题（AI 配置、权限、网络等）

## 联系支持 (Support)

如果问题持续存在，请提供：
1. 浏览器控制台的完整错误消息（现在应该是可读的）
2. 后端日志输出
3. 具体的操作步骤
