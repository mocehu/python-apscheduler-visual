from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, func
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class JobLog(Base):
    __tablename__ = 'job_logs'

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String(255))
    status = Column(String(255))
    message = Column(Text)
    timestamp = Column(TIMESTAMP, server_default=func.now())
