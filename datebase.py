# db.py
import redis
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from urllib.parse import urlparse
from conf import DATABASE_URL, REDIS_URL

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


def get_redis():
    """
    获取 Redis 连接对象
    """
    # 解析REDIS_URL
    url = urlparse(REDIS_URL)

    # 获取连接配置
    redis_host = url.hostname
    redis_port = url.port
    redis_password = url.password
    redis_db = int(url.path.lstrip('/'))  # 将路径转换为数据库编号

    # 连接到Redis
    return redis.Redis(
        host=redis_host,
        port=redis_port,
        password=redis_password,
        db=redis_db
    )