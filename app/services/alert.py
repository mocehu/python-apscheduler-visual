import json
import logging
import smtplib
import time
import fnmatch
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import requests

from app.core.database import _session_factory, get_config_bool
from app.models.sql_model import AlertConfig, AlertChannel, AlertHistory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_job_fail_counts: Dict[str, int] = {}
_job_last_alert_time: Dict[str, datetime] = {}


def reset_fail_count(job_id: str):
    _job_fail_counts[job_id] = 0


def increment_fail_count(job_id: str) -> int:
    _job_fail_counts[job_id] = _job_fail_counts.get(job_id, 0) + 1
    return _job_fail_counts[job_id]


def get_fail_count(job_id: str) -> int:
    return _job_fail_counts.get(job_id, 0)


def can_alert(job_id: str, cooldown_minutes: int) -> bool:
    last_alert = _job_last_alert_time.get(job_id)
    if not last_alert:
        return True
    return datetime.utcnow() - last_alert >= timedelta(minutes=cooldown_minutes)


def mark_alert_sent(job_id: str):
    _job_last_alert_time[job_id] = datetime.utcnow()


def match_job_id(pattern: Optional[str], job_id: str) -> bool:
    if not pattern or pattern == "*":
        return True
    return fnmatch.fnmatch(job_id, pattern)


def build_alert_message(job_id: str, rule_type: str, error: Optional[str], duration: Optional[float], threshold: Optional[int] = None) -> str:
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    
    if rule_type == "timeout":
        duration_str = f"{int(duration or 0)}ms" if duration else "未知"
        threshold_str = f"{threshold * 1000}ms" if threshold else "未知"
        return f"""【任务超时告警】
任务ID: {job_id}
触发规则: 执行超时
执行时长: {duration_str}（超过阈值 {threshold_str})
发生时间: {timestamp}"""
    
    fail_count = get_fail_count(job_id)
    duration_str = f"{int(duration or 0)}ms" if duration else "未知"
    
    rule_name_map = {
        "single_fail": "单次失败",
        "consecutive_fail": f"连续失败{threshold}次",
        "job_removed": "任务不存在"
    }
    rule_name = rule_name_map.get(rule_type, rule_type)
    
    return f"""【任务告警】
任务ID: {job_id}
触发规则: {rule_name}
执行状态: 失败
连续失败次数: {fail_count}
错误信息: {error or '未知'}
执行时长: {duration_str}
发生时间: {timestamp}"""


def send_webhook_alert(channel: AlertChannel, message: str) -> Dict[str, Any]:
    config = json.loads(channel.config) if isinstance(channel.config, str) else channel.config
    url = config.get("url")
    method = config.get("method", "POST")
    headers = config.get("headers", {})
    body_template = config.get("body_template", '{"message": "{message}"}')
    
    escaped_message = json.dumps(message, ensure_ascii=False)[1:-1]
    body = body_template.replace("{message}", escaped_message)
    
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            data=body,
            timeout=10
        )
        if response.status_code >= 200 and response.status_code < 300:
            return {"success": True, "message": f"HTTP {response.status_code}"}
        else:
            return {"success": False, "message": f"HTTP {response.status_code}: {response.text[:200]}"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def send_email_alert(channel: AlertChannel, message: str) -> Dict[str, Any]:
    config = json.loads(channel.config) if isinstance(channel.config, str) else channel.config
    smtp_host = config.get("smtp_host")
    smtp_port = config.get("smtp_port", 465)
    smtp_user = config.get("smtp_user")
    smtp_pass = config.get("smtp_pass")
    from_addr = config.get("from_addr", smtp_user)
    to_addr = config.get("to_addr", [])
    
    if isinstance(to_addr, str):
        to_addr = [addr.strip() for addr in to_addr.split(",") if addr.strip()]
    
    subject = f"[告警] 任务异常通知 - {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
    
    try:
        msg = MIMEText(message, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = ", ".join(to_addr)
        
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_addr, to_addr, msg.as_string())
        
        return {"success": True, "message": f"邮件已发送至 {', '.join(to_addr)}"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def record_alert_history(job_id: str, rule_type: str, channel_type: str, channel_id: int, status: bool, message: str, error: Optional[str] = None):
    db = _session_factory()
    try:
        history = AlertHistory(
            job_id=job_id,
            rule_type=rule_type,
            channel_type=channel_type,
            channel_id=channel_id,
            status=status,
            message=message,
            error=error
        )
        db.add(history)
        db.commit()
    except Exception as e:
        logger.error(f"记录告警历史失败: {e}")
    finally:
        db.close()


def get_alert_configs(db) -> List[AlertConfig]:
    return db.query(AlertConfig).filter(AlertConfig.enabled == True).all()


def get_alert_channel(db, channel_id: int) -> Optional[AlertChannel]:
    return db.query(AlertChannel).filter(AlertChannel.id == channel_id).first()


def get_alert_channels_by_ids(db, channel_ids: List[int]) -> List[AlertChannel]:
    return db.query(AlertChannel).filter(AlertChannel.id.in_(channel_ids), AlertChannel.enabled == True).all()


def check_and_alert(job_id: str, status: bool, duration: Optional[float] = None, error: Optional[str] = None, job_exists: bool = True):
    db = _session_factory()
    try:
        if not get_config_bool(db, "alert_enabled", True):
            return
        
        configs = get_alert_configs(db)
        
        for config in configs:
            if not match_job_id(config.job_id, job_id):
                continue
            
            should_alert = False
            threshold = config.threshold
            
            if config.rule_type == "single_fail" and not status:
                should_alert = True
            
            elif config.rule_type == "consecutive_fail" and not status:
                fail_count = increment_fail_count(job_id)
                if fail_count >= (threshold or 3):
                    should_alert = True
            
            elif config.rule_type == "timeout" and duration and duration > (threshold or 60) * 1000:
                should_alert = True
            
            elif config.rule_type == "job_removed" and not job_exists:
                should_alert = True
            
            if should_alert and can_alert(job_id, config.cooldown_minutes):
                message = build_alert_message(job_id, config.rule_type, error, duration, threshold)
                
                channel_ids = json.loads(config.channels) if isinstance(config.channels, str) else config.channels
                channels = get_alert_channels_by_ids(db, channel_ids)
                
                for channel in channels:
                    result = {"success": False, "message": "未知错误"}
                    
                    if channel.type == "webhook":
                        result = send_webhook_alert(channel, message)
                    elif channel.type == "email":
                        result = send_email_alert(channel, message)
                    
                    record_alert_history(
                        job_id=job_id,
                        rule_type=config.rule_type,
                        channel_type=channel.type,
                        channel_id=channel.id,
                        status=result["success"],
                        message=message,
                        error=result["message"] if not result["success"] else None
                    )
                    
                    if result["success"]:
                        logger.info(f"告警发送成功: {job_id} -> {channel.name}")
                    else:
                        logger.error(f"告警发送失败: {job_id} -> {channel.name}: {result['message']}")
                
                mark_alert_sent(job_id)
        
        if status:
            reset_fail_count(job_id)
    
    except Exception as e:
        logger.error(f"告警检查失败: {e}")
    finally:
        db.close()


def test_alert_channel(channel: AlertChannel) -> Dict[str, Any]:
    test_message = f"""【测试告警】
这是一条测试消息，用于验证告警渠道配置是否正确。
发送时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"""
    
    if channel.type == "webhook":
        return send_webhook_alert(channel, test_message)
    elif channel.type == "email":
        return send_email_alert(channel, test_message)
    else:
        return {"success": False, "message": f"不支持的渠道类型: {channel.type}"}