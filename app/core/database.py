import redis
import logging
from datetime import datetime, timedelta
from sqlalchemy import create_engine, event, inspect, func, delete
from sqlalchemy.orm import sessionmaker, scoped_session, Session

from app.core.conf import DATABASE_URL, DB_TYPE, REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_DB
from app.models.sql_model import Base, JobLog, SystemConfig, DEFAULT_CONFIG

logger = logging.getLogger(__name__)

if DB_TYPE == "sqlite":
    engine = create_engine(DATABASE_URL)
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_redis():
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD if REDIS_PASSWORD else None,
        db=REDIS_DB
    )


def init_db():
    Base.metadata.create_all(bind=engine)
    _init_default_config()
    logger.info("数据库表初始化完成")


def _init_default_config():
    db = SessionLocal()
    try:
        for key, config in DEFAULT_CONFIG.items():
            existing = db.query(SystemConfig).filter(SystemConfig.key == key).first()
            if not existing:
                db.add(SystemConfig(
                    key=key,
                    value=config["value"],
                    description=config["description"]
                ))
        db.commit()
    except Exception as e:
        logger.error(f"初始化默认配置失败: {e}")
        db.rollback()
    finally:
        db.close()


def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    _init_default_config()
    logger.info("数据库已重置")


def get_db_status():
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    expected_tables = [table.__tablename__ for table in Base.metadata.tables.values()]
    return {table: table in existing_tables for table in expected_tables}


def get_config(db: Session, key: str, default: str = None) -> str:
    config = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    if config and config.value:
        return config.value
    return default or DEFAULT_CONFIG.get(key, {}).get("value", "")


def get_config_int(db: Session, key: str, default: int = 0) -> int:
    try:
        return int(get_config(db, key, str(default)))
    except (ValueError, TypeError):
        return default


def get_config_bool(db: Session, key: str, default: bool = False) -> bool:
    value = get_config(db, key, str(default).lower())
    return value.lower() in ("true", "1", "yes")


def set_config(db: Session, key: str, value: str) -> SystemConfig:
    config = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    if config:
        config.value = value
        config.updated_at = datetime.utcnow()
    else:
        config = SystemConfig(key=key, value=value)
        db.add(config)
    db.commit()
    return config


def get_all_config(db: Session) -> dict:
    configs = db.query(SystemConfig).all()
    result = {}
    for config in configs:
        result[config.key] = {
            "value": config.value,
            "description": config.description,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None
        }
    for key, default in DEFAULT_CONFIG.items():
        if key not in result:
            result[key] = {
                "value": default["value"],
                "description": default["description"],
                "updated_at": None
            }
    return result


def update_config_batch(db: Session, config_dict: dict) -> dict:
    updated = {}
    for key, value in config_dict.items():
        if key in DEFAULT_CONFIG:
            config = set_config(db, key, str(value))
            updated[key] = {
                "value": config.value,
                "description": config.description,
                "updated_at": config.updated_at.isoformat() if config.updated_at else None
            }
    return updated


def cleanup_old_logs(db: Session, retention_days: int = None, max_count: int = None) -> dict:
    if retention_days is None:
        retention_days = get_config_int(db, "log_retention_days", 30)
    if max_count is None:
        max_count = get_config_int(db, "log_max_count", 100000)
    
    result = {"deleted_by_age": 0, "deleted_by_count": 0}
    
    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
    deleted_by_age = db.execute(
        delete(JobLog).where(JobLog.timestamp < cutoff_date)
    )
    result["deleted_by_age"] = deleted_by_age.rowcount
    
    total_count = db.query(func.count(JobLog.id)).scalar()
    if total_count > max_count:
        excess_count = total_count - max_count
        oldest_ids = db.query(JobLog.id).order_by(JobLog.timestamp.asc()).limit(excess_count).all()
        oldest_id_list = [id[0] for id in oldest_ids]
        deleted_by_count = db.execute(
            delete(JobLog).where(JobLog.id.in_(oldest_id_list))
        )
        result["deleted_by_count"] = deleted_by_count.rowcount
    
    db.commit()
    logger.info(f"日志清理完成: 按时间删除 {result['deleted_by_age']} 条, 按数量删除 {result['deleted_by_count']} 条")
    return result


def get_log_stats(db: Session) -> dict:
    retention_days = get_config_int(db, "log_retention_days", 30)
    max_count = get_config_int(db, "log_max_count", 100000)
    
    total_count = db.query(func.count(JobLog.id)).scalar()
    success_count = db.query(func.count(JobLog.id)).where(JobLog.status == True).scalar()
    fail_count = db.query(func.count(JobLog.id)).where(JobLog.status == False).scalar()
    
    oldest_log = db.query(JobLog).order_by(JobLog.timestamp.asc()).first()
    newest_log = db.query(JobLog).order_by(JobLog.timestamp.desc()).first()
    
    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
    expired_count = db.query(func.count(JobLog.id)).where(JobLog.timestamp < cutoff_date).scalar()
    
    return {
        "total_count": total_count,
        "success_count": success_count,
        "fail_count": fail_count,
        "oldest_timestamp": oldest_log.timestamp.isoformat() if oldest_log else None,
        "newest_timestamp": newest_log.timestamp.isoformat() if newest_log else None,
        "expired_count": expired_count,
        "retention_days": retention_days,
        "max_count": max_count
    }


def clear_all_logs(db: Session) -> int:
    deleted = db.execute(delete(JobLog))
    db.commit()
    logger.info(f"已清除所有日志: {deleted.rowcount} 条")
    return deleted.rowcount