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


DEFAULT_CONFIG = {
    "log_retention_days": {"value": "30", "description": "日志保留天数"},
    "log_auto_cleanup": {"value": "true", "description": "是否自动清理日志"},
    "log_cleanup_hour": {"value": "3", "description": "自动清理执行时间（小时，0-23）"},
    "log_max_count": {"value": "100000", "description": "最大日志数量"},
    "api_key_enabled": {"value": "true", "description": "是否启用 API Key 认证"},
    "api_key": {"value": "", "description": "API 密钥（为空时使用环境变量 API_KEY）"},
}