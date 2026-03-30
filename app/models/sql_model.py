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
} 
