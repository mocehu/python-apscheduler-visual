import json
import logging
import redis
from datetime import datetime, timedelta
from sqlalchemy import create_engine, event, inspect, func, delete
from sqlalchemy.orm import sessionmaker, scoped_session, Session

from app.core.conf import DATABASE_URL, DB_TYPE, REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_DB
from app.models.sql_model import (
    AIMessage,
    AISession,
    AIToolCall,
    AlertChannel,
    AlertConfig,
    AlertHistory,
    Base,
    CustomTask,
    DEFAULT_CONFIG,
    JobLog,
    SystemConfig,
)

logger = logging.getLogger(__name__)

if DB_TYPE == "sqlite":
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

_session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
SessionLocal = scoped_session(_session_factory)


def get_db():
    db = _session_factory()
    try:
        yield db
    finally:
        db.close()


def get_isolated_db():
    db = _session_factory()
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


def get_configs_by_prefix(db: Session, prefix: str) -> dict:
    configs = get_all_config(db)
    return {key: value for key, value in configs.items() if key.startswith(prefix)}


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


def create_ai_session(
    db: Session,
    session_id: str,
    title: str = None,
    provider: str = 'openai_compatible',
    model: str = 'gpt-4o-mini',
    mode: str = 'draft',
) -> AISession:
    session = AISession(
        id=session_id,
        title=title,
        provider=provider,
        model=model,
        mode=mode,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_ai_session(db: Session, session_id: str) -> AISession:
    return db.query(AISession).filter(AISession.id == session_id).first()


def list_ai_sessions(db: Session, limit: int = 50):
    return db.query(AISession).order_by(AISession.updated_at.desc()).limit(limit).all()


def delete_ai_session(db: Session, session_id: str) -> bool:
    db.query(AIMessage).filter(AIMessage.session_id == session_id).delete()
    db.query(AIToolCall).filter(AIToolCall.session_id == session_id).delete()
    deleted = db.query(AISession).filter(AISession.id == session_id).delete()
    db.commit()
    return bool(deleted)


def add_ai_message(db: Session, session_id: str, role: str, content: str) -> AIMessage:
    message = AIMessage(session_id=session_id, role=role, content=content)
    db.add(message)

    session = get_ai_session(db, session_id)
    if session:
        if not session.title and role == 'user':
            session.title = content[:60]
        session.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(message)
    return message


def list_ai_messages(db: Session, session_id: str, limit: int = 100):
    return (
        db.query(AIMessage)
        .filter(AIMessage.session_id == session_id)
        .order_by(AIMessage.created_at.asc())
        .limit(limit)
        .all()
    )


def add_ai_tool_call(
    db: Session,
    session_id: str,
    tool_name: str,
    tool_args: dict = None,
    tool_result: dict = None,
    status: str = 'success',
    message_id: int = None,
) -> AIToolCall:
    tool_call = AIToolCall(
        session_id=session_id,
        message_id=message_id,
        tool_name=tool_name,
        tool_args=json.dumps(tool_args or {}, ensure_ascii=False),
        tool_result=json.dumps(tool_result or {}, ensure_ascii=False),
        status=status,
    )
    db.add(tool_call)
    db.commit()
    db.refresh(tool_call)
    return tool_call


def list_ai_tool_calls(db: Session, session_id: str, limit: int = 100):
    return (
        db.query(AIToolCall)
        .filter(AIToolCall.session_id == session_id)
        .order_by(AIToolCall.created_at.asc())
        .limit(limit)
        .all()
    )


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


def create_alert_channel(db: Session, name: str, type: str, config: dict, enabled: bool = True) -> AlertChannel:
    channel = AlertChannel(
        name=name,
        type=type,
        config=json.dumps(config, ensure_ascii=False),
        enabled=enabled
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


def get_alert_channel(db: Session, channel_id: int) -> AlertChannel:
    return db.query(AlertChannel).filter(AlertChannel.id == channel_id).first()


def get_alert_channel_by_name(db: Session, name: str) -> AlertChannel:
    return db.query(AlertChannel).filter(AlertChannel.name == name).first()


def get_alert_channels(db: Session, enabled_only: bool = False) -> list:
    query = db.query(AlertChannel)
    if enabled_only:
        query = query.filter(AlertChannel.enabled == True)
    return query.order_by(AlertChannel.created_at.desc()).all()


def update_alert_channel(db: Session, channel_id: int, name: str = None, config: dict = None, enabled: bool = None) -> AlertChannel:
    channel = get_alert_channel(db, channel_id)
    if not channel:
        return None
    if name is not None:
        channel.name = name
    if config is not None:
        channel.config = json.dumps(config, ensure_ascii=False)
    if enabled is not None:
        channel.enabled = enabled
    db.commit()
    db.refresh(channel)
    return channel


def delete_alert_channel(db: Session, channel_id: int) -> bool:
    deleted = db.query(AlertChannel).filter(AlertChannel.id == channel_id).delete()
    db.commit()
    return bool(deleted)


def create_alert_config(db: Session, rule_type: str, channels: list, job_id: str = None, threshold: int = None, cooldown_minutes: int = 30, enabled: bool = True) -> AlertConfig:
    config = AlertConfig(
        job_id=job_id,
        rule_type=rule_type,
        threshold=threshold,
        channels=json.dumps(channels, ensure_ascii=False),
        cooldown_minutes=cooldown_minutes,
        enabled=enabled
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def get_alert_config(db: Session, config_id: int) -> AlertConfig:
    return db.query(AlertConfig).filter(AlertConfig.id == config_id).first()


def get_alert_configs(db: Session, enabled_only: bool = False) -> list:
    query = db.query(AlertConfig)
    if enabled_only:
        query = query.filter(AlertConfig.enabled == True)
    return query.order_by(AlertConfig.created_at.desc()).all()


def update_alert_config(db: Session, config_id: int, job_id: str = None, rule_type: str = None, threshold: int = None, channels: list = None, cooldown_minutes: int = None, enabled: bool = None) -> AlertConfig:
    config = get_alert_config(db, config_id)
    if not config:
        return None
    if job_id is not None:
        config.job_id = job_id
    if rule_type is not None:
        config.rule_type = rule_type
    if threshold is not None:
        config.threshold = threshold
    if channels is not None:
        config.channels = json.dumps(channels, ensure_ascii=False)
    if cooldown_minutes is not None:
        config.cooldown_minutes = cooldown_minutes
    if enabled is not None:
        config.enabled = enabled
    db.commit()
    db.refresh(config)
    return config


def delete_alert_config(db: Session, config_id: int) -> bool:
    deleted = db.query(AlertConfig).filter(AlertConfig.id == config_id).delete()
    db.commit()
    return bool(deleted)


def get_alert_history(db: Session, history_id: int) -> AlertHistory:
    return db.query(AlertHistory).filter(AlertHistory.id == history_id).first()


def list_alert_history(db: Session, job_id: str = None, status: bool = None, channel_type: str = None, start_time: datetime = None, end_time: datetime = None, page: int = 1, limit: int = 20) -> dict:
    query = db.query(AlertHistory)
    
    if job_id:
        query = query.filter(AlertHistory.job_id.ilike(f"%{job_id}%"))
    if status is not None:
        query = query.filter(AlertHistory.status == status)
    if channel_type:
        query = query.filter(AlertHistory.channel_type == channel_type)
    if start_time:
        query = query.filter(AlertHistory.sent_at >= start_time)
    if end_time:
        query = query.filter(AlertHistory.sent_at <= end_time)
    
    total_count = query.count()
    
    offset = (page - 1) * limit
    logs = query.order_by(AlertHistory.sent_at.desc()).offset(offset).limit(limit).all()
    
    return {"count": total_count, "logs": logs}


def cleanup_old_alert_history(db: Session, retention_days: int = None) -> int:
    if retention_days is None:
        retention_days = get_config_int(db, "alert_history_retention_days", 30)
    
    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
    deleted = db.execute(delete(AlertHistory).where(AlertHistory.sent_at < cutoff_date))
    db.commit()
    logger.info(f"告警历史清理完成: 删除 {deleted.rowcount} 条")
    return deleted.rowcount
