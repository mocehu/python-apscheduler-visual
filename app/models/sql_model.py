from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, Boolean, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class JobLog(Base):
    __tablename__ = 'job_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(128), nullable=False)
    status = Column(Boolean, nullable=False)
    message = Column(Text, nullable=False)
    duration = Column(Float, nullable=True)
    output = Column(Text, nullable=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"<JobLog(id={self.id}, job_id={self.job_id}, status={self.status}, message={self.message}, duration={self.duration}, timestamp={self.timestamp})>"


class SystemConfig(Base):
    __tablename__ = 'system_config'

    key = Column(String(128), primary_key=True)
    value = Column(Text, nullable=False)
    description = Column(String(255), nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<SystemConfig(key={self.key}, value={self.value})>"


class AISession(Base):
    __tablename__ = 'ai_sessions'

    id = Column(String(64), primary_key=True)
    title = Column(String(255), nullable=True)
    provider = Column(String(64), nullable=False, default='openai_compatible')
    model = Column(String(128), nullable=False, default='gpt-4o-mini')
    mode = Column(String(32), nullable=False, default='draft')
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<AISession(id={self.id}, provider={self.provider}, model={self.model})>"


class AIMessage(Base):
    __tablename__ = 'ai_messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False, index=True)
    role = Column(String(32), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"<AIMessage(id={self.id}, session_id={self.session_id}, role={self.role})>"


class AIToolCall(Base):
    __tablename__ = 'ai_tool_calls'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False, index=True)
    message_id = Column(Integer, nullable=True)
    tool_name = Column(String(128), nullable=False)
    tool_args = Column(Text, nullable=True)
    tool_result = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default='success')
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"<AIToolCall(id={self.id}, session_id={self.session_id}, tool_name={self.tool_name})>"


class CustomTask(Base):
    __tablename__ = 'custom_tasks'

    name = Column(String(128), primary_key=True)
    category = Column(String(64), nullable=False, default='custom')
    description = Column(String(255), nullable=True)
    code = Column(Text, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<CustomTask(name={self.name}, category={self.category}, enabled={self.enabled})>"


class AlertChannel(Base):
    __tablename__ = 'alert_channels'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False, unique=True)
    type = Column(String(32), nullable=False)
    config = Column(Text, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<AlertChannel(id={self.id}, name={self.name}, type={self.type}, enabled={self.enabled})>"


class AlertConfig(Base):
    __tablename__ = 'alert_configs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(128), nullable=True)
    rule_type = Column(String(32), nullable=False)
    threshold = Column(Integer, nullable=True)
    channels = Column(Text, nullable=False)
    cooldown_minutes = Column(Integer, nullable=False, default=30)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<AlertConfig(id={self.id}, job_id={self.job_id}, rule_type={self.rule_type}, enabled={self.enabled})>"


class AlertHistory(Base):
    __tablename__ = 'alert_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(128), nullable=False)
    rule_type = Column(String(32), nullable=False)
    channel_type = Column(String(32), nullable=False)
    channel_id = Column(Integer, nullable=True)
    status = Column(Boolean, nullable=False)
    message = Column(Text, nullable=False)
    sent_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    error = Column(Text, nullable=True)

    def __repr__(self):
        return f"<AlertHistory(id={self.id}, job_id={self.job_id}, rule_type={self.rule_type}, status={self.status})>"


DEFAULT_CONFIG = {
    "log_retention_days": {"value": "30", "description": "日志保留天数"},
    "log_auto_cleanup": {"value": "true", "description": "是否自动清理日志"},
    "log_cleanup_hour": {"value": "3", "description": "自动清理执行时间（小时，0-23）"},
    "log_max_count": {"value": "100000", "description": "最大日志数量"},
    "api_key_enabled": {"value": "true", "description": "是否启用 API Key 认证"},
    "api_key": {"value": "", "description": "API 密钥（为空时使用环境变量 API_KEY）"},
    "ai_enabled": {"value": "true", "description": "是否启用 AI 功能"},
    "ai_provider": {"value": "openai_compatible", "description": "AI 提供商"},
    "ai_base_url": {"value": "https://api.openai.com/v1", "description": "AI 接口 Base URL"},
    "ai_api_key": {"value": "", "description": "AI API Key（为空时使用环境变量）"},
    "ai_model": {"value": "gpt-4o-mini", "description": "默认 AI 模型"},
    "ai_allow_execute": {"value": "false", "description": "是否允许 AI 直接执行变更"},
    "ai_stream_enabled": {"value": "true", "description": "是否启用 AI 流式输出"},
    "ai_agent_api_key": {"value": "", "description": "外部 AI Agent 调用密钥"},
    "ai_max_history_messages": {"value": "12", "description": "AI 上下文最大历史消息数"},
    "custom_task_timeout": {"value": "30", "description": "自定义任务执行超时时间（秒）"},
    "custom_task_forbidden_modules": {"value": "pickle,marshal,shelve,ctypes", "description": "禁止导入的模块列表（逗号分隔）"},
    "custom_task_forbidden_builtins": {"value": "__import__,compile,exec,eval,breakpoint", "description": "禁止调用的内置函数列表（逗号分隔）"},
    "alert_enabled": {"value": "true", "description": "是否启用告警功能"},
    "alert_history_retention_days": {"value": "30", "description": "告警历史保留天数"},
} 
