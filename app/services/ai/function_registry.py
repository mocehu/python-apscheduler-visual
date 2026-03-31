import json
import uuid
from datetime import datetime
from typing import Any, Dict, List

from app.core.database import _session_factory, get_all_config, get_config, get_log_stats
from app.services.scheduler import (
    add_job,
    get_all_jobs,
    get_job_by_id,
    pause_job,
    remove_job,
    resume_job,
    update_job,
)
from app.services.tasks import get_task_categories, get_task_info


def _generate_job_id(func: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_uuid = uuid.uuid4().hex[:6]
    return f"{func}_{timestamp}_{short_uuid}"


def _format_trigger_description(trigger: str, trigger_args: Dict[str, Any]) -> str:
    if trigger == "cron":
        parts = []
        if "day_of_week" in trigger_args:
            day_map = {"mon": "周一", "tue": "周二", "wed": "周三", "thu": "周四", "fri": "周五", "sat": "周六", "sun": "周日"}
            parts.append(day_map.get(trigger_args["day_of_week"], trigger_args["day_of_week"]))
        if "day" in trigger_args:
            parts.append(f"每月{trigger_args['day']}号")
        hour = trigger_args.get("hour", "*")
        minute = trigger_args.get("minute", 0)
        if hour != "*":
            parts.append(f"{hour:02d}:{minute:02d}")
        return " ".join(parts) if parts else "定时执行"
    elif trigger == "interval":
        parts = []
        if trigger_args.get("weeks"):
            parts.append(f"每{trigger_args['weeks']}周")
        if trigger_args.get("days"):
            parts.append(f"每{trigger_args['days']}天")
        if trigger_args.get("hours"):
            parts.append(f"每{trigger_args['hours']}小时")
        if trigger_args.get("minutes"):
            parts.append(f"每{trigger_args['minutes']}分钟")
        if trigger_args.get("seconds"):
            parts.append(f"每{trigger_args['seconds']}秒")
        return " ".join(parts) if parts else "间隔执行"
    elif trigger == "date":
        return f"一次性执行: {trigger_args.get('run_date', '指定时间')}"
    return trigger


def _tool_list_jobs() -> Dict[str, Any]:
    return {"jobs": get_all_jobs()}


def _tool_get_job(job_id: str) -> Dict[str, Any]:
    return {"job": get_job_by_id(job_id)}


def _tool_search_jobs(keyword: str) -> Dict[str, Any]:
    jobs = get_all_jobs()
    filtered = [job for job in jobs if keyword.lower() in job.get('id', '').lower() or keyword.lower() in (job.get('name') or '').lower()]
    return {"jobs": filtered, "keyword": keyword}


def _tool_list_available_tasks() -> Dict[str, Any]:
    return {
        "tasks": get_task_info(),
        "categories": get_task_categories(),
    }


def _tool_get_current_time() -> Dict[str, Any]:
    now = datetime.now()
    return {
        "datetime": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": now.strftime("%A"),
        "weekday_cn": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()],
        "timestamp": int(now.timestamp()),
    }


def _tool_get_logs(job_id: str = None, status: bool = None, limit: int = 10) -> Dict[str, Any]:
    from app.models.sql_model import JobLog
    db = _session_factory()
    try:
        query = db.query(JobLog)
        if job_id:
            query = query.filter(JobLog.job_id.ilike(f"%{job_id}%"))
        if status is not None:
            query = query.filter(JobLog.status == status)
        logs = query.order_by(JobLog.timestamp.desc()).limit(limit).all()
        return {
            "logs": [
                {
                    "id": log.id,
                    "job_id": log.job_id,
                    "status": log.status,
                    "message": log.message,
                    "duration": log.duration,
                    "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                }
                for log in logs
            ],
            "count": len(logs),
        }
    finally:
        db.close()


def _tool_get_log_stats() -> Dict[str, Any]:
    db = _session_factory()
    try:
        stats = get_log_stats(db)
        return stats
    finally:
        db.close()


def _tool_get_config(key: str = None) -> Dict[str, Any]:
    db = _session_factory()
    try:
        if key:
            value = get_config(db, key)
            return {"key": key, "value": value}
        return get_all_config(db)
    finally:
        db.close()


def _tool_generate_code(
    description: str,
    func_name: str = None,
    category: str = "custom",
) -> Dict[str, Any]:
    """
    根据用户需求生成自定义任务代码
    
    Args:
        description: 用户想要实现的功能描述
        func_name: 函数名（可选，默认根据描述生成）
        category: 分类，默认 custom
    """
    from app.services.custom_tasks import validate_task_code, check_code_security, DEFAULT_FORBIDDEN_MODULES, DEFAULT_FORBIDDEN_BUILTINS
    
    forbidden_modules = ",".join(DEFAULT_FORBIDDEN_MODULES)
    forbidden_builtins = ",".join(DEFAULT_FORBIDDEN_BUILTINS)
    
    return {
        "action": "generate_code",
        "payload": {
            "description": description,
            "func_name": func_name,
            "category": category,
            "forbidden_modules": forbidden_modules,
            "forbidden_builtins": forbidden_builtins,
        },
        "display": {
            "title": "生成自定义任务代码",
            "fields": [
                {"label": "功能描述", "value": description},
                {"label": "函数名", "value": func_name or "自动生成"},
                {"label": "分类", "value": category},
            ],
            "warning": "生成代码后将经过安全检查，请在确认后保存",
        },
        "confirm_text": "保存代码",
        "cancel_text": "取消",
    }


def _tool_review_code(code: str, func_name: str = None) -> Dict[str, Any]:
    """
    审查分析代码
    
    Args:
        code: 要审查的 Python 代码
        func_name: 函数名（可选）
    """
    from app.services.custom_tasks import check_code_security, validate_task_code
    
    security_result = check_code_security(code)
    validation_result = validate_task_code(code, func_name or "temp_func") if func_name else {"valid": True, "params": None, "error": None}
    
    issues = []
    if not security_result["safe"]:
        for error in security_result["errors"]:
            issues.append({"level": "error", "message": error})
    for warning in security_result["warnings"]:
        issues.append({"level": "warning", "message": warning})
    
    return {
        "action": "review_code",
        "payload": {
            "security": {
                "safe": security_result["safe"],
                "errors": security_result["errors"],
                "warnings": security_result["warnings"],
            },
            "validation": {
                "valid": validation_result["valid"],
                "params": validation_result["params"],
                "error": validation_result["error"],
            },
            "issues": issues,
        },
        "display": {
            "title": "代码审查结果",
            "fields": [
                {"label": "安全检查", "value": "通过" if security_result["safe"] else "未通过"},
                {"label": "语法验证", "value": "通过" if validation_result["valid"] else "未通过"},
                {"label": "问题数量", "value": f"{len(issues)} 个"},
            ],
            "issues": issues,
        },
        "confirm_text": "确认",
        "cancel_text": "取消",
    }


def _tool_draft_create_job(
    func: str,
    trigger: str,
    trigger_args: Dict[str, Any] = None,
    args: List[Any] = None,
    kwargs: Dict[str, Any] = None,
    name: str = None,
) -> Dict[str, Any]:
    trigger_desc = _format_trigger_description(trigger, trigger_args or {})
    return {
        "action": "create_job",
        "payload": {
            "func": func,
            "trigger": trigger,
            "trigger_args": trigger_args or {},
            "args": args or [],
            "kwargs": kwargs or {},
            "name": name,
        },
        "display": {
            "title": "创建任务",
            "fields": [
                {"label": "任务函数", "value": func},
                {"label": "触发方式", "value": trigger_desc},
            ],
        },
        "confirm_text": "确认创建",
        "cancel_text": "取消",
    }


def _tool_draft_update_job(
    job_id: str,
    func: str,
    trigger: str,
    trigger_args: Dict[str, Any] = None,
    args: List[Any] = None,
    kwargs: Dict[str, Any] = None,
    name: str = None,
) -> Dict[str, Any]:
    trigger_desc = _format_trigger_description(trigger, trigger_args or {})
    return {
        "action": "update_job",
        "payload": {
            "job_id": job_id,
            "func": func,
            "trigger": trigger,
            "trigger_args": trigger_args or {},
            "args": args or [],
            "kwargs": kwargs or {},
            "name": name,
        },
        "display": {
            "title": "修改任务",
            "fields": [
                {"label": "任务ID", "value": job_id},
                {"label": "任务函数", "value": func},
                {"label": "触发方式", "value": trigger_desc},
            ],
        },
        "confirm_text": "确认修改",
        "cancel_text": "取消",
    }


def _tool_draft_update_config(configs: Dict[str, str]) -> Dict[str, Any]:
    return {
        "action": "update_config",
        "payload": {"configs": configs},
        "display": {
            "title": "修改配置",
            "fields": [
                {"label": "配置项", "value": ", ".join(configs.keys())},
            ],
        },
        "confirm_text": "确认修改",
        "cancel_text": "取消",
    }


def _tool_draft_delete_job(job_id: str) -> Dict[str, Any]:
    return {
        "action": "delete_job",
        "payload": {"job_id": job_id},
        "display": {
            "title": "删除任务",
            "fields": [
                {"label": "任务ID", "value": job_id},
            ],
            "warning": "此操作不可撤销",
        },
        "confirm_text": "确认删除",
        "cancel_text": "取消",
    }


def _tool_draft_pause_job(job_id: str) -> Dict[str, Any]:
    return {
        "action": "pause_job",
        "payload": {"job_id": job_id},
        "display": {
            "title": "暂停任务",
            "fields": [
                {"label": "任务ID", "value": job_id},
            ],
        },
        "confirm_text": "确认暂停",
        "cancel_text": "取消",
    }


def _tool_draft_resume_job(job_id: str) -> Dict[str, Any]:
    return {
        "action": "resume_job",
        "payload": {"job_id": job_id},
        "display": {
            "title": "恢复任务",
            "fields": [
                {"label": "任务ID", "value": job_id},
            ],
        },
        "confirm_text": "确认恢复",
        "cancel_text": "取消",
    }


def _tool_execute_create_job(
    func: str,
    trigger: str,
    job_id: str = None,
    trigger_args: Dict[str, Any] = None,
    args: List[Any] = None,
    kwargs: Dict[str, Any] = None,
    name: str = None,
) -> Dict[str, Any]:
    try:
        if not job_id:
            job_id = _generate_job_id(func)
        add_job(
            func_name=func,
            trigger=trigger,
            args=args or [],
            kwargs=kwargs or {},
            job_id=job_id,
            name=name,
            **(trigger_args or {})
        )
        return {"success": True, "job_id": job_id, "message": "任务创建成功"}
    except Exception as e:
        return {"success": False, "job_id": job_id, "error": str(e)}


def _tool_execute_update_job(
    job_id: str,
    func: str,
    trigger: str,
    trigger_args: Dict[str, Any] = None,
    args: List[Any] = None,
    kwargs: Dict[str, Any] = None,
    name: str = None,
) -> Dict[str, Any]:
    try:
        update_job(
            func=func,
            job_id=job_id,
            trigger=trigger,
            trigger_args=trigger_args or {},
            args=args or [],
            kwargs=kwargs or {},
            name=name
        )
        return {"success": True, "job_id": job_id, "message": "任务更新成功"}
    except Exception as e:
        return {"success": False, "job_id": job_id, "error": str(e)}


def _tool_execute_update_config(configs: Dict[str, str]) -> Dict[str, Any]:
    from app.core.database import set_config, DEFAULT_CONFIG
    db = _session_factory()
    try:
        updated = {}
        for key, value in configs.items():
            if key in DEFAULT_CONFIG:
                set_config(db, key, value)
                updated[key] = value
        db.commit()
        return {"success": True, "updated": updated, "message": f"已更新 {len(updated)} 个配置项"}
    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e)}
    finally:
        db.close()


def _tool_execute_delete_job(job_id: str) -> Dict[str, Any]:
    try:
        remove_job(job_id)
        return {"success": True, "job_id": job_id, "message": "任务已删除"}
    except Exception as e:
        return {"success": False, "job_id": job_id, "error": str(e)}


def _tool_execute_pause_job(job_id: str) -> Dict[str, Any]:
    try:
        pause_job(job_id)
        return {"success": True, "job_id": job_id, "message": "任务已暂停"}
    except Exception as e:
        return {"success": False, "job_id": job_id, "error": str(e)}


def _tool_execute_resume_job(job_id: str) -> Dict[str, Any]:
    try:
        resume_job(job_id)
        return {"success": True, "job_id": job_id, "message": "任务已恢复"}
    except Exception as e:
        return {"success": False, "job_id": job_id, "error": str(e)}


TOOL_HANDLERS = {
    "list_jobs": _tool_list_jobs,
    "get_job": _tool_get_job,
    "search_jobs": _tool_search_jobs,
    "list_available_tasks": _tool_list_available_tasks,
    "get_logs": _tool_get_logs,
    "get_log_stats": _tool_get_log_stats,
    "get_config": _tool_get_config,
    "get_current_time": _tool_get_current_time,
    "generate_code": _tool_generate_code,
    "review_code": _tool_review_code,
    "draft_create_job": _tool_draft_create_job,
    "draft_update_job": _tool_draft_update_job,
    "draft_delete_job": _tool_draft_delete_job,
    "draft_pause_job": _tool_draft_pause_job,
    "draft_resume_job": _tool_draft_resume_job,
    "draft_update_config": _tool_draft_update_config,
    "execute_create_job": _tool_execute_create_job,
    "execute_update_job": _tool_execute_update_job,
    "execute_delete_job": _tool_execute_delete_job,
    "execute_pause_job": _tool_execute_pause_job,
    "execute_resume_job": _tool_execute_resume_job,
    "execute_update_config": _tool_execute_update_config,
}


def get_tool_schemas() -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "list_jobs",
                "description": "获取当前所有计划任务",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_job",
                "description": "根据任务ID获取单个计划任务详情",
                "parameters": {
                    "type": "object",
                    "properties": {"job_id": {"type": "string", "description": "任务ID"}},
                    "required": ["job_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_jobs",
                "description": "根据关键词搜索任务",
                "parameters": {
                    "type": "object",
                    "properties": {"keyword": {"type": "string", "description": "搜索关键词"}},
                    "required": ["keyword"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_available_tasks",
                "description": "获取可用任务函数和分类",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_current_time",
                "description": "获取当前日期和时间",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_logs",
                "description": "获取任务执行日志",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string", "description": "任务ID筛选"},
                        "status": {"type": "boolean", "description": "状态筛选"},
                        "limit": {"type": "integer", "description": "返回数量限制", "default": 10},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_log_stats",
                "description": "获取日志统计信息",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_config",
                "description": "获取系统配置",
                "parameters": {
                    "type": "object",
                    "properties": {"key": {"type": "string", "description": "配置键名，不传则返回全部"}},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "generate_code",
                "description": "根据用户需求生成自定义任务代码。生成后需要用户确认才能保存。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string", "description": "用户想要实现的功能描述"},
                        "func_name": {"type": "string", "description": "函数名（可选，默认根据描述生成）"},
                        "category": {"type": "string", "description": "分类，默认 custom"},
                    },
                    "required": ["description"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "review_code",
                "description": "审查分析代码的安全性、语法和逻辑问题",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "要审查的 Python 代码"},
                        "func_name": {"type": "string", "description": "函数名（可选，用于参数验证）"},
                    },
                    "required": ["code"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "draft_create_job",
                "description": "生成创建计划任务草案，不直接执行。根据用户描述的触发时间生成正确的 trigger 和 trigger_args。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "func": {"type": "string", "description": "任务函数名，必须从 list_available_tasks 返回的列表中选择"},
                        "trigger": {"type": "string", "enum": ["cron", "interval", "date"], "description": "触发器类型: cron(定时)/interval(间隔)/date(一次性)"},
                        "trigger_args": {
                            "type": "object",
                            "description": "触发器参数。cron: {hour, minute, day_of_week(mon/tue/wed/thu/fri/sat/sun), day, month}。interval: {hours, minutes, seconds, days, weeks}。date: {run_date: 'YYYY-MM-DD HH:MM:SS'}",
                            "examples": [
                                {"hour": 8, "minute": 0},
                                {"day_of_week": "mon", "hour": 9},
                                {"hours": 1},
                                {"run_date": "2024-12-25 10:00:00"}
                            ]
                        },
                        "args": {"type": "array", "description": "任务函数的位置参数"},
                        "kwargs": {"type": "object", "description": "任务函数的关键字参数"},
                        "name": {"type": "string", "description": "任务名称，可选"},
                    },
                    "required": ["func", "trigger"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "draft_update_job",
                "description": "生成修改计划任务草案，不直接执行",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string", "description": "任务ID"},
                        "func": {"type": "string", "description": "任务函数名"},
                        "trigger": {"type": "string", "description": "触发器类型"},
                        "trigger_args": {"type": "object", "description": "触发器参数"},
                        "args": {"type": "array", "description": "位置参数"},
                        "kwargs": {"type": "object", "description": "关键字参数"},
                        "name": {"type": "string", "description": "任务名称"},
                    },
                    "required": ["job_id", "func", "trigger"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "draft_delete_job",
                "description": "生成删除任务草案，需用户确认后执行",
                "parameters": {
                    "type": "object",
                    "properties": {"job_id": {"type": "string", "description": "任务ID"}},
                    "required": ["job_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "draft_pause_job",
                "description": "生成暂停任务草案，需用户确认后执行",
                "parameters": {
                    "type": "object",
                    "properties": {"job_id": {"type": "string", "description": "任务ID"}},
                    "required": ["job_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "draft_resume_job",
                "description": "生成恢复任务草案，需用户确认后执行",
                "parameters": {
                    "type": "object",
                    "properties": {"job_id": {"type": "string", "description": "任务ID"}},
                    "required": ["job_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "draft_update_config",
                "description": "生成更新配置草案，需用户确认后执行",
                "parameters": {
                    "type": "object",
                    "properties": {"configs": {"type": "object", "description": "配置键值对"}},
                    "required": ["configs"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "execute_create_job",
                "description": "直接创建计划任务（需要ai_allow_execute=true）。job_id 可选，不传则自动生成。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "func": {"type": "string", "description": "任务函数名"},
                        "trigger": {"type": "string", "description": "触发器类型: cron/interval/date"},
                        "job_id": {"type": "string", "description": "任务ID（可选，不传则自动生成）"},
                        "trigger_args": {"type": "object", "description": "触发器参数"},
                        "args": {"type": "array", "description": "位置参数"},
                        "kwargs": {"type": "object", "description": "关键字参数"},
                        "name": {"type": "string", "description": "任务名称"},
                    },
                    "required": ["func", "trigger"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "execute_update_job",
                "description": "直接修改计划任务（需要ai_allow_execute=true）",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string", "description": "任务ID"},
                        "func": {"type": "string", "description": "任务函数名"},
                        "trigger": {"type": "string", "description": "触发器类型"},
                        "trigger_args": {"type": "object", "description": "触发器参数"},
                        "args": {"type": "array", "description": "位置参数"},
                        "kwargs": {"type": "object", "description": "关键字参数"},
                        "name": {"type": "string", "description": "任务名称"},
                    },
                    "required": ["job_id", "func", "trigger"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "execute_delete_job",
                "description": "直接删除任务（需要ai_allow_execute=true）",
                "parameters": {
                    "type": "object",
                    "properties": {"job_id": {"type": "string", "description": "任务ID"}},
                    "required": ["job_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "execute_pause_job",
                "description": "直接暂停任务（需要ai_allow_execute=true）",
                "parameters": {
                    "type": "object",
                    "properties": {"job_id": {"type": "string", "description": "任务ID"}},
                    "required": ["job_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "execute_resume_job",
                "description": "直接恢复任务（需要ai_allow_execute=true）",
                "parameters": {
                    "type": "object",
                    "properties": {"job_id": {"type": "string", "description": "任务ID"}},
                    "required": ["job_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "execute_update_config",
                "description": "直接更新配置（需要ai_allow_execute=true）",
                "parameters": {
                    "type": "object",
                    "properties": {"configs": {"type": "object", "description": "配置键值对"}},
                    "required": ["configs"],
                },
            },
        },
    ]


def call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        raise ValueError(f"未知工具: {name}")
    return handler(**arguments)


def get_readonly_tools() -> List[str]:
    return [
        "list_jobs",
        "get_job",
        "search_jobs",
        "list_available_tasks",
        "get_logs",
        "get_log_stats",
        "get_config",
        "get_current_time",
        "generate_code",
        "review_code",
    ]


def get_draft_tools() -> List[str]:
    return [
        "draft_create_job",
        "draft_update_job",
        "draft_delete_job",
        "draft_pause_job",
        "draft_resume_job",
        "draft_update_config",
    ]


def get_execute_tools() -> List[str]:
    return [
        "execute_create_job",
        "execute_update_job",
        "execute_delete_job",
        "execute_pause_job",
        "execute_resume_job",
        "execute_update_config",
    ]