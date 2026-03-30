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
