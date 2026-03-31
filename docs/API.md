# API 文档

## AI 接口

### 接口列表

| 接口 | 方法 | 说明 |
|------|------|------|
| `/ai/chat` | POST | AI 对话，返回文本和工具调用结果 |
| `/ai/chat/stream` | POST | AI 流式对话（SSE），支持上下文记忆 |
| `/ai/sessions` | GET | 获取 AI 会话列表 |
| `/ai/sessions/{session_id}` | GET | 获取 AI 会话详情 |
| `/ai/sessions/{session_id}` | DELETE | 删除 AI 会话 |
| `/ai/models` | GET | 获取可用模型配置 |
| `/ai/tools` | GET | 获取 AI 可调用工具列表 |
| `/ai/config` | GET | 获取 AI 配置 |
| `/ai/config` | PUT | 更新 AI 配置 |
| `/ai/generate-code` | POST | AI 生成代码（同步） |
| `/ai/generate-code/stream` | POST | AI 流式生成代码（SSE） |
| `/ai/review-code` | POST | AI 审查代码（同步） |
| `/ai/review-code/stream` | POST | AI 流式审查代码（SSE） |

### 上下文记忆（多轮对话）

系统支持多轮对话上下文记忆，通过 `session_id` 实现：

**使用方式**：

1. **首次对话**：不传 `session_id`，系统自动创建新会话
2. **获取 session_id**：从响应中获取（非流式：`data.session_id`；流式：第一条 SSE 消息 `{"type": "session", "session_id": "xxx"}`）
3. **后续对话**：传递该 `session_id`，系统自动加载历史消息

**请求示例**：

```bash
# 首次对话（不传 session_id）
curl -X POST http://localhost:8000/ai/chat \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"message": "你好"}'

# 响应包含 session_id
# {"code":200, "data":{"session_id":"abc123", "reply":"你好！"}}

# 后续对话（传递 session_id）
curl -X POST http://localhost:8000/ai/chat \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"message": "我刚才说了什么", "session_id": "abc123"}'
```

**历史消息限制**：通过 `ai_max_history_messages` 配置（默认 12 条）

### 流式对话（SSE）

```javascript
// 前端处理 SSE 流
const eventSource = new EventSource('/ai/chat/stream');
let sessionId = null;

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'session') {
    sessionId = data.session_id;  // 保存 session_id
  } else if (data.type === 'content') {
    // 处理流式内容
  } else if (data.type === 'done') {
    eventSource.close();
    // 下次请求使用 sessionId
  }
};
```

### SSE 事件类型

| type | 说明 | 数据 |
|------|------|------|
| `session` | 会话信息 | `{session_id, model}` |
| `content` | 文本内容 | `{content}` |
| `tool_call` | 工具调用 | `{name, arguments, result}` |
| `draft` | 操作草案 | `{draft}` |
| `error` | 错误 | `{message, code}` |
| `done` | 完成 | `{reply}` |

### 草案确认格式

AI 生成操作草案时，会返回标准格式，方便前端解析：

```json
{
  "type": "draft",
  "draft": {
    "action": "create_job",
    "payload": {
      "func": "auto_cleanup_logs",
      "trigger": "cron",
      "trigger_args": {"hour": 8, "minute": 0}
    },
    "display": {
      "title": "创建任务",
      "fields": [
        { "label": "任务函数", "value": "auto_cleanup_logs" },
        { "label": "触发方式", "value": "每天 08:00" }
      ]
    },
    "confirm_text": "确认创建",
    "cancel_text": "取消"
  }
}
```

| 字段 | 说明 |
|------|------|
| `action` | 操作类型：create_job / update_job / delete_job / pause_job / resume_job / update_config |
| `payload` | 操作参数，执行时传给后端 |
| `display.title` | 操作标题 |
| `display.fields` | 展示字段列表，每项包含 label 和 value |
| `display.warning` | 警告信息（可选） |
| `confirm_text` | 确认按钮文本 |
| `cancel_text` | 取消按钮文本 |

### 操作类型说明

| action | 说明 | payload 字段 |
|--------|------|-------------|
| `create_job` | 创建任务 | `func`, `trigger`, `trigger_args`, `args`, `kwargs`, `name` |
| `update_job` | 修改任务 | `job_id`, `func`, `trigger`, `trigger_args`, `args`, `kwargs`, `name` |
| `delete_job` | 删除任务 | `job_id` |
| `pause_job` | 暂停任务 | `job_id` |
| `resume_job` | 恢复任务 | `job_id` |
| `update_config` | 修改配置 | `configs` |

### 触发器参数格式

**cron 触发器**（定时执行）：
- "每天早8点" → `trigger="cron", trigger_args={"hour": 8, "minute": 0}`
- "每周一9点" → `trigger="cron", trigger_args={"day_of_week": "mon", "hour": 9}`
- "每月1号0点" → `trigger="cron", trigger_args={"day": 1, "hour": 0}`
- 参数: year, month, day, week, day_of_week, hour, minute, second

**interval 触发器**（间隔执行）：
- "每小时" → `trigger="interval", trigger_args={"hours": 1}`
- "每30分钟" → `trigger="interval", trigger_args={"minutes": 30}`
- 参数: weeks, days, hours, minutes, seconds

**date 触发器**（一次性执行）：
- "2024-12-25 10:00" → `trigger="date", trigger_args={"run_date": "2024-12-25 10:00:00"}`

### AI 代码生成

**接口**：`POST /ai/generate-code`

**请求体**：
```json
{
  "description": "发送邮件通知",
  "func_name": "send_email",
  "category": "custom"
}
```

**参数说明**：
| 参数 | 必填 | 说明 |
|------|------|------|
| `description` | 是 | 功能需求描述 |
| `func_name` | 否 | 函数名，不传则自动生成 |
| `category` | 否 | 分类，默认 custom |

**响应示例**：
```json
{
  "code": 200,
  "data": {
    "success": true,
    "code": "def send_email(to: str, subject: str, body: str):\n    print(f\"发送邮件到 {to}\")\n    return {\"output\": \"邮件已发送\", \"status\": true}",
    "func_name": "send_email",
    "category": "custom"
  }
}
```

### AI 代码审查

**接口**：`POST /ai/review-code`

**请求体**：
```json
{
  "code": "def hello(name):\n    print(f'Hello, {name}!')\n    return name",
  "func_name": "hello"
}
```

**参数说明**：
| 参数 | 必填 | 说明 |
|------|------|------|
| `code` | 是 | 要审查的代码 |
| `func_name` | 否 | 函数名，用于参数验证 |

**响应示例**：
```json
{
  "code": 200,
  "data": {
    "success": true,
    "security": {
      "safe": true,
      "errors": [],
      "warnings": [],
      "suggestions": ["建议添加类型注解"],
      "summary": "代码安全，符合规范"
    },
    "has_issues": false
  }
}
```

### AI 流式生成代码

**接口**：`POST /ai/generate-code/stream`

**说明**：流式生成代码，适用于前端超时限制场景。使用 SSE（Server-Sent Events）返回数据。

**请求体**：与同步接口相同

**SSE 消息格式**：
```
data: {"type": "status", "message": "正在生成代码..."}

data: {"type": "content", "content": "def "}

data: {"type": "content", "content": "send_email"}

data: {"type": "done", "code": "def send_email(...): ...", "func_name": "send_email"}
```

**消息类型**：
| type | 说明 |
|------|------|
| `status` | 状态更新 |
| `content` | 生成的代码片段（逐字返回） |
| `done` | 完成，包含完整代码 |
| `error` | 错误 |

### AI 流式审查代码

**接口**：`POST /ai/review-code/stream`

**SSE 消息格式**：
```
data: {"type": "security", "safe": true, "errors": [], "warnings": []}

data: {"type": "status", "message": "正在分析代码..."}

data: {"type": "content", "content": "{"}

data: {"type": "done", "security": {...}, "has_issues": false}
```

**消息类型**：
| type | 说明 |
|------|------|
| `security` | 安全检查结果（立即返回） |
| `status` | 状态更新 |
| `content` | AI 分析内容片段 |
| `done` | 完成，包含完整审查结果 |
| `error` | 错误 |

## 任务管理接口

### 接口列表

| 接口 | 方法 | 说明 |
|------|------|------|
| `/jobs/` | GET | 获取所有任务列表 |
| `/jobs/{job_id}` | GET | 获取单个任务详情 |
| `/jobs/` | POST | 创建任务 |
| `/jobs/{job_id}` | PUT | 更新任务 |
| `/jobs/{job_id}` | DELETE | 删除任务 |
| `/jobs/{job_id}/pause` | POST | 暂停任务 |
| `/jobs/{job_id}/resume` | POST | 恢复任务 |

### 请求示例

```bash
# 获取所有任务
curl -X GET http://localhost:8000/jobs/ -H "X-API-Key: your-key"

# 创建任务
curl -X POST http://localhost:8000/jobs/ \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "my_task",
    "name": "我的任务",
    "func": "auto_cleanup_logs",
    "trigger": "cron",
    "trigger_args": {"hour": 8},
    "args": [],
    "kwargs": {}
  }'

# 暂停任务
curl -X POST http://localhost:8000/jobs/my_task/pause \
  -H "X-API-Key: your-key"

# 恢复任务
curl -X POST http://localhost:8000/jobs/my_task/resume \
  -H "X-API-Key: your-key"
```

## 日志接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/logs/` | GET | 获取任务执行日志 |
| `/log-stats/` | GET | 获取日志统计信息 |
| `/cleanup-logs/` | POST | 手动清理过期日志 |
| `/clear-logs/` | POST | 清除所有日志（危险操作） |

## 系统配置接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/config/` | GET | 获取系统配置 |
| `/config/{key}` | GET | 获取单个配置 |
| `/config/{key}` | PUT | 更新配置 |

## 其他接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/tasks/` | GET | 获取可用任务函数列表 |
| `/version/` | GET | 获取版本信息 |
| `/check-update/` | GET | 检查更新 |
| `/reload-tasks/` | POST | 热加载任务（默认重新加载自定义任务） |

## 自定义任务接口

### 接口列表

| 接口 | 方法 | 说明 |
|------|------|------|
| `/custom-tasks/` | GET | 获取自定义任务列表 |
| `/custom-tasks/{name}` | GET | 获取自定义任务详情 |
| `/custom-tasks/` | POST | 创建自定义任务 |
| `/custom-tasks/{name}` | PUT | 更新自定义任务 |
| `/custom-tasks/{name}` | DELETE | 删除自定义任务 |
| `/custom-tasks/validate` | POST | 验证任务代码 |
| `/custom-tasks/security-config` | GET | 获取安全配置 |
| `/custom-tasks/security-config` | PUT | 更新安全配置 |

### 创建自定义任务

用户可以在页面上直接编写 Python 任务函数代码，无需修改后台文件。

**安全防护机制**：

系统采用多层安全防护，确保自定义任务代码安全执行：

1. **代码安全检查**：创建前进行 AST 语法分析，禁止：
   - 导入危险模块：`pickle`, `marshal`, `shelve`, `ctypes`
   - 调用危险函数：`__import__`, `compile`, `exec`, `eval`, `breakpoint`

2. **超时保护**：默认 30 秒超时，防止无限循环

3. **用户可配置**：可通过 `/custom-tasks/security-config` 接口自定义禁止列表

**允许的操作**：
- 系统命令执行：`os`, `subprocess`
- 网络请求：`requests`, `urllib`, `socket`
- 文件操作：`open`, `pathlib`
- 数据库操作：`sqlite3`, 以及各种数据库驱动
- 其他标准库模块

**请求示例**：

```bash
curl -X POST http://localhost:8000/custom-tasks/ \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "send_notification",
    "category": "notification",
    "description": "发送通知消息",
    "code": "def send_notification(title: str, message: str):\n    print(f\"通知: {title} - {message}\")\n    return {\"output\": f\"已发送: {title}\", \"status\": True}"
  }'
```

**代码规范**：

1. 函数名必须与 `name` 参数一致
2. 函数参数支持类型注解（可选）
3. 返回值可以是任意类型，建议返回 dict：
   - `output`: 输出内容
   - `status`: 执行状态（True/False）
   - `error`: 错误信息（可选）

**响应格式**：

```json
{
  "name": "send_notification",
  "category": "notification",
  "description": "发送通知消息",
  "code": "def send_notification(title: str, message: str): ...",
  "enabled": true,
  "created_at": "2026-03-31T10:00:00",
  "updated_at": "2026-03-31T10:00:00",
  "parameters": {
    "title": {"name": "title", "type": "str", "default": null, "required": true},
    "message": {"name": "message", "type": "str", "default": null, "required": true}
  },
  "is_used": false,
  "used_by_jobs": []
}
```

**字段说明**：

| 字段 | 说明 |
|------|------|
| `parameters` | 函数参数解析，包含参数名、类型、默认值、是否必填 |
| `is_used` | 是否被计划任务使用 |
| `used_by_jobs` | 使用该任务的计划任务 ID 列表 |

### 更新/删除自定义任务

**更新任务**：

```bash
curl -X PUT "http://localhost:8000/custom-tasks/send_notification?force=false" \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"description": "新的描述"}'
```

**参数说明**：
- `force`: 是否强制更新（即使任务正在被使用），默认 false

**删除任务**：

```bash
curl -X DELETE http://localhost:8000/custom-tasks/send_notification \
  -H "X-API-Key: your-key"
```

**注意**：如果任务正在被计划任务使用，更新和删除操作会被拒绝，返回错误信息。需要先删除相关计划任务，或使用 `force=true` 强制操作。
4. 使用 `print()` 输出的内容会被自动捕获
5. **禁止**导入外部模块或调用危险函数

**安全检查示例**：

```bash
# 尝试创建危险代码会被拒绝
curl -X POST http://localhost:8000/custom-tasks/ \
  -d '{
    "name": "hack",
    "code": "import os\ndef hack():\n    os.system(\"rm -rf /\")"
  }'

# 响应：{"code": 400, "msg": "代码安全检查失败: 禁止导入模块: os; 禁止使用 os.system"}
```

**验证代码**：

创建前可先验证代码语法和安全性：

```bash
curl -X POST http://localhost:8000/custom-tasks/validate \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my_task",
    "code": "def my_task(x: int):\n    return x * 2"
  }'

# 响应：{"code": 200, "data": {"valid": true, "params": {...}}
```

### 安全配置

用户可以自定义安全配置，包括超时时间、禁止模块和禁止函数列表。

**获取安全配置**：

```bash
curl http://localhost:8000/custom-tasks/security-config \
  -H "X-API-Key: your-key"

# 响应示例
{
  "code": 200,
  "data": {
    "timeout": 30,
    "forbidden_modules": ["os", "sys", "subprocess", ...],
    "forbidden_builtins": ["open", "eval", "exec", ...]
  }
}
```

**更新安全配置**：

```bash
# 设置超时时间为 60 秒
curl -X PUT "http://localhost:8000/custom-tasks/security-config?timeout=60" \
  -H "X-API-Key: your-key"

# 自定义禁止模块列表
curl -X PUT "http://localhost:8000/custom-tasks/security-config?forbidden_modules=os,subprocess,socket" \
  -H "X-API-Key: your-key"

# 自定义禁止函数列表
curl -X PUT "http://localhost:8000/custom-tasks/security-config?forbidden_builtins=open,eval,exec" \
  -H "X-API-Key: your-key"
```

**注意事项**：
- 超时时间范围：1-300 秒
- 清空禁止列表可允许更多操作，但会降低安全性
- 建议保留核心安全限制（如 `os`, `subprocess`, `open`, `eval` 等）

### 使用自定义任务

创建成功后，自定义任务会自动注册，可直接用于计划任务：

```bash
curl -X POST http://localhost:8000/add-job/ \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "func": "send_notification",
    "trigger": "cron",
    "job_id": "daily_notification",
    "trigger_args": {"hour": 9, "minute": 0},
    "args": ["每日提醒", "请检查待办事项"]
  }'
```
