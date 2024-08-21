from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, func, Boolean, Float, DateTime, UUID, BigInteger
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class JobLog(Base):
    __tablename__ = 'job_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, nullable=False)
    status = Column(Boolean, nullable=False)
    message = Column(String, nullable=False)
    duration = Column(Float, nullable=True)  # 执行耗时（秒）
    output = Column(String, nullable=True)  # 返回值
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"<JobLog(id={self.id}, job_id={self.job_id}, status={self.status}, message={self.message}, duration={self.duration}, output={self.output}, timestamp={self.timestamp})>"
