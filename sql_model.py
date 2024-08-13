from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, func, Boolean, Float, DateTime, UUID
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


class UencVoiaem(Base):
    __tablename__ = 'uenc_voiaem'

    id = Column(Integer, primary_key=True, autoincrement=True)
    protocol = Column(String(255), nullable=True)
    rec_ip = Column(String(255), nullable=True)
    dst_ip = Column(String(255), nullable=True)
    helper_uid = Column(String(255), nullable=True)
    occ_time = Column(DateTime, nullable=True)
    add_time = Column(DateTime, nullable=True)
    msg = Column(String(255), nullable=True)
    # 补充字段
    sub_range = Column(String(255), nullable=True, comment="订阅范围/IP段")
    sub_status = Column(String(255), nullable=True, default='0', comment="订阅状态,0未订阅,1已订阅")
    origin_type = Column(String(255), nullable=True, default='0', comment="获取方式,0自动,1手动")
    sync_time = Column(DateTime, nullable=False, server_default=func.now(), comment="数据同步时间")
