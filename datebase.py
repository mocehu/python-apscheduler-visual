# db.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

from conf import DATABASE_URL

# 创建引擎
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# 创建Session
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))


def get_db():
    """
    获取数据库会话
    :return: 数据库会话
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
