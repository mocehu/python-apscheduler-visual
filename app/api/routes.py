import json
import traceback
from datetime import datetime
from functools import wraps
from typing import Optional, Dict, Any, Callable

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import (
    delete_ai_session,
    get_ai_session,
    get_all_config,
    get_config,
    get_configs_by_prefix,
    get_db,
    list_ai_messages,
    list_ai_sessions,
    list_ai_tool_calls,
    set_config,
    update_config_batch,
    cleanup_old_logs,
    get_log_stats,
    clear_all_logs,
    create_alert_channel,
    get_alert_channel,
    get_alert_channel_by_name,
    get_alert_channels,
    update_alert_channel,
    delete_alert_channel,
    create_alert_config,
    get_alert_config,
    get_alert_configs,
    update_alert_config,
    delete_alert_config,
    list_alert_history,
)
from app.models.schemas import (
    AIChatRequest,
    AIChatResponse,
    AIConfigUpdateRequest,
    CodeGenerateRequest,
    CodeReviewRequest,
    AIMessageResponse,
    AISessionDetailResponse,
    AISessionResponse,
    AIToolCallResponse,
    AvailableTask,
    CronTrigger,
    CustomTaskCreate,
    CustomTaskResponse,
    CustomTaskUpdate,
    DateTrigger,
    IntervalTrigger,
    JobCreate,
    JobLogPage,
    JobLogResponse,
    ResponseModel,
    AlertChannelCreate,
    AlertChannelUpdate,
    AlertChannelResponse,
    AlertConfigCreate,
    AlertConfigUpdate,
    AlertConfigResponse,
    AlertHistoryResponse,
    AlertHistoryPage,
    AlertTestResponse,
)
from app.models.sql_model import JobLog, DEFAULT_CONFIG
from app.services.scheduler import add_job, remove_job, update_job, get_all_jobs, get_job_by_id, pause_job, resume_job, \
    scheduler
from app.services.scheduler import update_auto_cleanup_schedule
from app.services.ai.chat_service import chat_once, chat_stream
from app.services.ai.function_registry import get_tool_schemas
from app.services.tasks import get_task_info, get_task_categories, get_task, reload_tasks
from app.services.custom_tasks import (
    get_custom_task,
    get_custom_tasks,
    create_custom_task,
    update_custom_task,
    delete_custom_task,
    validate_task_code,
    load_custom_tasks,
)

router = APIRouter()


def api_error_handler(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            traceback.print_exc()
            return ResponseModel(code=400, msg=str(e))

    return wrapper


@router.post("/run-job-now/", summary="立即执行")
@api_error_handler
def run_job_now(job_id: str) -> ResponseModel:
    job = scheduler.get_job(job_id=job_id)
    if not job:
        return ResponseModel(code=404, msg=f"计划任务 {job_id} 不存在")

    job = scheduler.modify_job(job_id=job_id, next_run_time=datetime.now())

    return ResponseModel(data=job.id, msg=f"计划任务 {job_id} 已安排立即执行")


@router.get("/available-tasks/", summary="可用任务函数列表")
@api_error_handler
def list_available_tasks(category: Optional[str] = None) -> ResponseModel:
    all_tasks = get_task_info()

    if category:
        all_tasks = [task for task in all_tasks if task["category"] == category]

    available_tasks = []
    for task_info in all_tasks:
        available_tasks.append(
            AvailableTask(
                name=task_info["name"],
                category=task_info["category"],
                description=task_info["description"],
                parameters=len(task_info["parameters"]),
                is_custom=task_info.get("is_custom", False)
            )
        )

    categories = get_task_categories()

    return ResponseModel(
        data={
            "tasks": available_tasks,
            "categories": categories
        },
        msg="获取可用任务函数列表成功"
    )


@router.get("/available-tasks/{func_name}", summary="获取单个任务详情")
@api_error_handler
def get_available_task_endpoint(func_name: str) -> ResponseModel:
    task_info = get_task_info(func_name)
    if not task_info:
        return ResponseModel(code=404, msg=f"任务函数 '{func_name}' 不存在")

    return ResponseModel(
        data=AvailableTask(
            name=task_info["name"],
            category=task_info["category"],
            description=task_info["description"],
            parameters=task_info["parameters"],
            is_custom=task_info.get("is_custom", False)
        ),
        msg="获取任务详情成功"
    )


def _validate_trigger(job: JobCreate) -> Dict[str, Any]:
    trigger_args = job.trigger_args or {}
    if job.trigger == "cron":
        model = CronTrigger(**trigger_args)
    elif job.trigger == "interval":
        model = IntervalTrigger(**trigger_args)
    elif job.trigger == "date":
        model = DateTrigger(**trigger_args)
    else:
        raise ValueError(f"不支持的触发器类型 '{job.trigger}'")

    return {k: v for k, v in model.dict().items() if v is not None}


@router.post("/add-job/", summary="新建计划任务")
@api_error_handler
def create_job(job: JobCreate) -> ResponseModel:
    task_func = get_task(job.func)
    if not task_func:
        return ResponseModel(code=404, msg=f"任务函数 '{job.func}' 未找到")

    trigger_args = _validate_trigger(job)

    actual_job_id = add_job(
        func_name=job.func,
        trigger=job.trigger,
        args=job.args,
        kwargs=job.kwargs,
        job_id=job.job_id,
        name=job.name,
        **trigger_args
    )
    return ResponseModel(data={"job_id": actual_job_id, "name": job.name}, msg="计划任务已添加")


@router.post("/update-job/", summary="修改计划任务")
@api_error_handler
def modify_job(job: JobCreate) -> ResponseModel:
    job_id = job.get_job_id()
    if not job_id:
        return ResponseModel(code=400, msg="缺少任务 ID")
    
    job_obj = scheduler.get_job(job_id=job_id)
    if not job_obj:
        return ResponseModel(code=404, msg=f"计划任务 {job_id} 不存在")

    task_func = get_task(job.func)
    if not task_func:
        return ResponseModel(code=404, msg=f"任务函数 '{job.func}' 未找到")

    trigger_args = _validate_trigger(job)

    update_job(
        func=job.func,
        job_id=job_id,
        trigger=job.trigger,
        trigger_args=trigger_args,
        args=job.args,
        kwargs=job.kwargs,
        name=job.name
    )
    return ResponseModel(data={"job_id": job_id, "name": job.name}, msg="任务已更新")


@router.get("/pause-job/{job_id}", summary="暂停计划任务")
@api_error_handler
def pause_job_endpoint(job_id: str) -> ResponseModel:
    job = scheduler.get_job(job_id=job_id)
    if not job:
        return ResponseModel(code=404, msg=f"计划任务 {job_id} 不存在")

    pause_job(job_id)
    return ResponseModel(data=job_id, msg=f"计划任务 {job_id} 已暂停")


@router.get("/resume-job/{job_id}", summary="恢复（被暂停的）计划任务")
@api_error_handler
def resume_job_endpoint(job_id: str) -> ResponseModel:
    job = scheduler.get_job(job_id=job_id)
    if not job:
        return ResponseModel(code=404, msg=f"计划任务 {job_id} 不存在")

    resume_job(job_id)
    return ResponseModel(data=job_id, msg=f"计划任务 {job_id} 已恢复")


@router.get("/remove-job/{job_id}", summary="删除计划任务")
@api_error_handler
def delete_job(job_id: str) -> ResponseModel:
    job = scheduler.get_job(job_id=job_id)
    if not job:
        return ResponseModel(code=404, msg=f"计划任务 {job_id} 不存在")

    remove_job(job_id)
    return ResponseModel(data=job_id, msg="计划任务已移除")


@router.get("/jobs/", summary="计划任务列表")
@api_error_handler
def list_jobs() -> ResponseModel:
    jobs = get_all_jobs()
    return ResponseModel(data=jobs, msg="获取计划任务列表成功")


@router.get("/job/{job_id}", summary="获取单个任务详情")
@api_error_handler
def get_job_detail(job_id: str) -> ResponseModel:
    """根据任务ID获取任务详情"""
    job = get_job_by_id(job_id)
    if not job:
        return ResponseModel(code=404, msg=f"任务 {job_id} 不存在")
    return ResponseModel(data=job, msg="获取任务详情成功")


@router.get("/logs/", summary="任务日志")
@api_error_handler
def get_logs(
        job_id: Optional[str] = Query(None, description="任务ID进行模糊查找"),
        status: Optional[bool] = Query(None, description="日志状态进行筛选，例如True或False"),
        start_time: Optional[datetime] = Query(None, description="起始时间YYYY-MM-DDTHH:MM:SS"),
        end_time: Optional[datetime] = Query(None, description="结束时间"),
        page: int = Query(1, ge=1, description="页数，从1开始"),
        limit: int = Query(10, le=100, description="每页返回的日志数量"),
        db: Session = Depends(get_db)
) -> ResponseModel:
    query = db.query(JobLog)

    if job_id:
        query = query.filter(JobLog.job_id.ilike(f"%{job_id}%"))
    if status is not None:
        query = query.filter(JobLog.status == status)
    if start_time:
        query = query.filter(JobLog.timestamp >= start_time)
    if end_time:
        query = query.filter(JobLog.timestamp <= end_time)

    total_count = query.count()

    offset = (page - 1) * limit
    db_logs = query.order_by(JobLog.timestamp.desc()).offset(offset).limit(limit).all()

    logs = [JobLogResponse.model_validate(log) for log in db_logs]

    log_page = JobLogPage(count=total_count, logs=logs)
    return ResponseModel(data=log_page, msg="获取日志成功")


@router.get("/task-categories/", summary="获取任务函数分类")
@api_error_handler
def list_task_categories() -> ResponseModel:
    categories = get_task_categories()
    return ResponseModel(data=categories, msg="获取任务函数分类成功")


@router.get("/task-info/{task_name}", summary="获取任务函数详情")
@api_error_handler
def get_task_details(task_name: str) -> ResponseModel:
    task_info = get_task_info(task_name)
    if not task_info:
        return ResponseModel(code=404, msg=f"任务函数 {task_name} 不存在")

    return ResponseModel(data=task_info, msg="获取任务函数详情成功")


@router.get("/log-stats/", summary="日志统计")
@api_error_handler
def get_logs_statistics(db: Session = Depends(get_db)) -> ResponseModel:
    stats = get_log_stats(db)
    return ResponseModel(data=stats, msg="获取日志统计成功")


@router.post("/cleanup-logs/", summary="清理过期日志")
@api_error_handler
def cleanup_logs(
        retention_days: Optional[int] = Query(None, description="保留天数，默认使用配置值"),
        max_count: Optional[int] = Query(None, description="最大日志数，默认使用配置值"),
        db: Session = Depends(get_db)
) -> ResponseModel:
    result = cleanup_old_logs(db, retention_days, max_count)
    return ResponseModel(data=result,
                         msg=f"日志清理完成，共删除 {result['deleted_by_age'] + result['deleted_by_count']} 条")


@router.post("/clear-logs/", summary="清除所有日志")
@api_error_handler
def clear_logs(db: Session = Depends(get_db)) -> ResponseModel:
    deleted_count = clear_all_logs(db)
    return ResponseModel(data={"deleted_count": deleted_count}, msg=f"已清除 {deleted_count} 条日志")


@router.get("/config/", summary="获取所有配置")
@api_error_handler
def get_all_config_endpoint(db: Session = Depends(get_db)) -> ResponseModel:
    configs = get_all_config(db)
    return ResponseModel(data=configs, msg="获取配置成功")


@router.get("/config/{key}", summary="获取单个配置")
@api_error_handler
def get_config_endpoint(key: str, db: Session = Depends(get_db)) -> ResponseModel:
    if key not in DEFAULT_CONFIG:
        return ResponseModel(code=404, msg=f"配置项 '{key}' 不存在")

    value = get_config(db, key)
    return ResponseModel(data={"key": key, "value": value}, msg="获取配置成功")


@router.put("/config/{key}", summary="更新单个配置")
@api_error_handler
def update_config_endpoint(key: str, value: str, db: Session = Depends(get_db)) -> ResponseModel:
    if key not in DEFAULT_CONFIG:
        return ResponseModel(code=404, msg=f"配置项 '{key}' 不存在")

    config = set_config(db, key, value)

    if key in ("log_auto_cleanup", "log_cleanup_hour"):
        update_auto_cleanup_schedule()

    return ResponseModel(
        data={"key": config.key, "value": config.value, "updated_at": config.updated_at.isoformat()},
        msg="配置更新成功"
    )


@router.post("/config/", summary="批量更新配置")
@api_error_handler
def update_config_batch_endpoint(configs: Dict[str, str], db: Session = Depends(get_db)) -> ResponseModel:
    updated = update_config_batch(db, configs)

    cleanup_keys = {"log_auto_cleanup", "log_cleanup_hour"}
    if cleanup_keys.intersection(configs.keys()):
        update_auto_cleanup_schedule()

    return ResponseModel(data=updated, msg=f"已更新 {len(updated)} 个配置项")


@router.get("/version/", summary="获取版本信息")
@api_error_handler
def get_version() -> ResponseModel:
    """获取当前版本信息"""
    from app.core.conf import VERSION, GITHUB_REPO
    return ResponseModel(
        data={
            "version": VERSION,
            "github_repo": GITHUB_REPO
        },
        msg="获取版本信息成功"
    )


@router.get("/check-update/", summary="检查更新")
@api_error_handler
def check_update_endpoint(force: bool = Query(False, description="是否强制检查（不使用缓存）")) -> ResponseModel:
    """检查是否有新版本"""
    from app.services.update_checker import check_update

    result = check_update(use_cache=not force)
    return ResponseModel(data=result, msg="检查更新完成")


@router.get("/release-notes/", summary="获取更新日志")
@api_error_handler
def get_release_notes(
        all: bool = Query(False, description="是否获取所有版本，默认只获取最新版本")
) -> ResponseModel:
    """从 GitHub 获取更新日志"""
    from app.services.update_checker import fetch_github_release, fetch_github_releases

    if all:
        releases = fetch_github_releases(limit=10)
        if releases:
            return ResponseModel(
                data={"releases": releases},
                msg="获取更新日志成功"
            )
        else:
            return ResponseModel(code=404, msg="无法获取更新日志，请检查后台配置或网络")
    else:
        release = fetch_github_release()
        if release:
            return ResponseModel(data=release, msg="获取更新日志成功")
        else:
            return ResponseModel(code=404, msg="无法获取更新日志，请检查后台配置或网络")


@router.post("/ai/chat", summary="AI 对话")
@api_error_handler
def ai_chat(request: AIChatRequest, db: Session = Depends(get_db)) -> ResponseModel:
    if not get_config(db, "ai_enabled", "true").lower() == 'true':
        return ResponseModel(code=403, msg="AI 功能未启用")

    result = chat_once(
        db,
        message=request.message,
        session_id=request.session_id or None,
        model=request.model or None,
        mode=request.mode,
    )
    return ResponseModel(data=AIChatResponse(**result), msg="AI 处理完成")


@router.post("/ai/chat/stream", summary="AI 流式对话")
@api_error_handler
def ai_chat_stream(request: AIChatRequest):
    def event_stream():
        from app.core.database import _session_factory
        db = _session_factory()
        try:
            if not get_config(db, "ai_enabled", "true").lower() == 'true':
                yield f"data: {json.dumps({'type': 'error', 'message': 'AI 功能未启用'}, ensure_ascii=False)}\n\n"
                return

            for chunk in chat_stream(
                    db,
                    message=request.message,
                    session_id=request.session_id or None,
                    model=request.model or None,
                    mode=request.mode,
            ):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/ai/sessions", summary="AI 会话列表")
@api_error_handler
def get_ai_sessions_endpoint(db: Session = Depends(get_db)) -> ResponseModel:
    sessions = list_ai_sessions(db)
    data = [AISessionResponse.model_validate(item) for item in sessions]
    return ResponseModel(data=data, msg="获取 AI 会话成功")


@router.get("/ai/sessions/{session_id}", summary="AI 会话详情")
@api_error_handler
def get_ai_session_endpoint(session_id: str, db: Session = Depends(get_db)) -> ResponseModel:
    session = get_ai_session(db, session_id)
    if not session:
        return ResponseModel(code=404, msg=f"AI 会话 {session_id} 不存在")

    messages = [AIMessageResponse.model_validate(item) for item in list_ai_messages(db, session_id)]
    tool_calls = [AIToolCallResponse.model_validate(item) for item in list_ai_tool_calls(db, session_id)]
    data = AISessionDetailResponse(
        session=AISessionResponse.model_validate(session),
        messages=messages,
        tool_calls=tool_calls,
    )
    return ResponseModel(data=data, msg="获取 AI 会话详情成功")


@router.delete("/ai/sessions/{session_id}", summary="删除 AI 会话")
@api_error_handler
def delete_ai_session_endpoint(session_id: str, db: Session = Depends(get_db)) -> ResponseModel:
    deleted = delete_ai_session(db, session_id)
    if not deleted:
        return ResponseModel(code=404, msg=f"AI 会话 {session_id} 不存在")
    return ResponseModel(data={"session_id": session_id}, msg="AI 会话已删除")


@router.get("/ai/models", summary="获取 AI 模型配置")
@api_error_handler
def get_ai_models_endpoint(db: Session = Depends(get_db)) -> ResponseModel:
    models = {
        "global": ["GPT 5.4 Pro", "Claude Haiku 4.5", "Gemini 3.1 Pro"],
        "china": ["GLM-5", "MiniMax M2.7", "MiMo V2 Pro"],
        "custom": [],
    }
    current = {
        "provider": get_config(db, "ai_provider", "volcengine"),
        "model": get_config(db, "ai_model", "GPT 5.4 Pro"),
    }
    return ResponseModel(data={"models": models, "current": current}, msg="获取 AI 模型成功")


@router.get("/ai/tools", summary="获取 AI 工具列表")
@api_error_handler
def get_ai_tools_endpoint() -> ResponseModel:
    return ResponseModel(data={"tools": get_tool_schemas()}, msg="获取 AI 工具成功")


@router.get("/ai/config", summary="获取 AI 配置")
@api_error_handler
def get_ai_config_endpoint(db: Session = Depends(get_db)) -> ResponseModel:
    return ResponseModel(data=get_configs_by_prefix(db, "ai_"), msg="获取 AI 配置成功")


@router.put("/ai/config", summary="更新 AI 配置")
@api_error_handler
def update_ai_config_endpoint(request: AIConfigUpdateRequest, db: Session = Depends(get_db)) -> ResponseModel:
    changes = {key: value for key, value in request.model_dump().items() if value is not None}
    updated = update_config_batch(db, changes)
    return ResponseModel(data=updated, msg=f"已更新 {len(updated)} 个 AI 配置项")


@router.post("/ai/generate-code", summary="AI 生成代码")
@api_error_handler
def ai_generate_code_endpoint(request: CodeGenerateRequest, db: Session = Depends(get_db)) -> ResponseModel:
    from app.services.ai.chat_service import generate_code
    result = generate_code(
        db,
        description=request.description,
        func_name=request.func_name,
        category=request.category
    )
    if result["success"]:
        return ResponseModel(data=result, msg="代码生成成功")
    return ResponseModel(code=400, msg=result.get("error", "代码生成失败"))


@router.post("/ai/review-code", summary="AI 审查代码")
@api_error_handler
def ai_review_code_endpoint(request: CodeReviewRequest, db: Session = Depends(get_db)) -> ResponseModel:
    from app.services.ai.chat_service import review_code
    result = review_code(
        db,
        code=request.code,
        func_name=request.func_name
    )
    return ResponseModel(data=result, msg="代码审查完成")


@router.post("/ai/generate-code/stream", summary="AI 流式生成代码")
def ai_generate_code_stream_endpoint(request: CodeGenerateRequest, db: Session = Depends(get_db)):
    from app.services.ai.chat_service import generate_code_stream

    def event_stream():
        for chunk in generate_code_stream(
                db,
                description=request.description,
                func_name=request.func_name,
                category=request.category
        ):
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/ai/review-code/stream", summary="AI 流式审查代码")
def ai_review_code_stream_endpoint(request: CodeReviewRequest, db: Session = Depends(get_db)):
    from app.services.ai.chat_service import review_code_stream

    def event_stream():
        for chunk in review_code_stream(
                db,
                code=request.code,
                func_name=request.func_name
        ):
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/reload-tasks/", summary="热加载任务模块")
@api_error_handler
def reload_tasks_endpoint(
        packages: Optional[str] = Query(None, description="要加载的包名，多个用逗号分隔"),
        directories: Optional[str] = Query(None, description="要扫描的目录路径，多个用逗号分隔"),
        clear_existing: bool = Query(False, description="是否清除现有任务注册表"),
        db: Session = Depends(get_db)
) -> ResponseModel:
    """
    热加载任务模块，无需重启服务器
    
    - packages: 要加载的 Python 包名，如 "app.tasks"，多个用逗号分隔
    - directories: 要扫描的目录路径，多个用逗号分隔
    - clear_existing: 是否清除现有任务注册表（谨慎使用，会影响正在运行的任务）
    
    不传参数时，默认重新加载自定义任务
    """
    package_list = [p.strip() for p in packages.split(",") if p.strip()] if packages else None
    directory_list = [d.strip() for d in directories.split(",") if d.strip()] if directories else None

    if not package_list and not directory_list:
        result = load_custom_tasks(db)
        return ResponseModel(data=result, msg=f"重新加载自定义任务完成，共 {len(result['loaded'])} 个")

    result = reload_tasks(
        packages=package_list,
        directories=directory_list,
        clear_existing=clear_existing
    )

    return ResponseModel(data=result, msg=f"任务重载完成，共 {result['total_tasks']} 个任务")


@router.get("/custom-tasks/", summary="自定义任务列表")
@api_error_handler
def list_custom_tasks_endpoint(
        enabled_only: bool = Query(False, description="只返回已启用的任务"),
        db: Session = Depends(get_db)
) -> ResponseModel:
    from app.services.custom_tasks import is_task_used, get_task_parameters
    tasks = get_custom_tasks(db, enabled_only=enabled_only)

    data = []
    for task in tasks:
        usage = is_task_used(task.name)
        params = get_task_parameters(task.code, task.name)
        task_dict = {
            "name": task.name,
            "category": task.category,
            "description": task.description,
            "code": task.code,
            "enabled": task.enabled,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "parameters": params,
            "is_used": usage["used"],
            "used_by_jobs": usage["jobs"]
        }
        data.append(task_dict)

    return ResponseModel(data=data, msg="获取自定义任务列表成功")


@router.get("/custom-tasks/security-config", summary="获取自定义任务安全配置")
@api_error_handler
def get_custom_task_security_config_endpoint(db: Session = Depends(get_db)) -> ResponseModel:
    from app.services.custom_tasks import get_security_config
    config = get_security_config(db)
    return ResponseModel(data={
        "timeout": config["timeout"],
        "forbidden_modules": list(config["forbidden_modules"]),
        "forbidden_builtins": list(config["forbidden_builtins"]),
    }, msg="获取安全配置成功")


@router.put("/custom-tasks/security-config", summary="更新自定义任务安全配置")
@api_error_handler
def update_custom_task_security_config_endpoint(
        timeout: Optional[int] = Query(None, description="执行超时时间（秒）"),
        forbidden_modules: Optional[str] = Query(None, description="禁止导入的模块列表（逗号分隔）"),
        forbidden_builtins: Optional[str] = Query(None, description="禁止调用的内置函数列表（逗号分隔）"),
        db: Session = Depends(get_db)
) -> ResponseModel:
    updated = {}

    if timeout is not None:
        if timeout < 1 or timeout > 300:
            return ResponseModel(code=400, msg="超时时间必须在 1-300 秒之间")
        set_config(db, "custom_task_timeout", str(timeout))
        updated["timeout"] = timeout

    if forbidden_modules is not None:
        set_config(db, "custom_task_forbidden_modules", forbidden_modules)
        updated["forbidden_modules"] = [m.strip() for m in forbidden_modules.split(",") if m.strip()]

    if forbidden_builtins is not None:
        set_config(db, "custom_task_forbidden_builtins", forbidden_builtins)
        updated["forbidden_builtins"] = [b.strip() for b in forbidden_builtins.split(",") if b.strip()]

    if not updated:
        return ResponseModel(code=400, msg="未提供任何配置项")

    return ResponseModel(data=updated, msg=f"已更新 {len(updated)} 个安全配置项")


@router.post("/custom-tasks/validate", summary="验证任务代码")
@api_error_handler
def validate_task_code_endpoint(request: CustomTaskCreate) -> ResponseModel:
    result = validate_task_code(request.code, request.name)
    if result["valid"]:
        return ResponseModel(data={"valid": True, "params": result["params"]}, msg="代码验证通过")
    return ResponseModel(code=400, msg=result["error"])


@router.post("/custom-tasks/reload", summary="重新加载自定义任务")
@router.get("/custom-tasks/{name}", summary="获取自定义任务详情")
@api_error_handler
def get_custom_task_endpoint(name: str, db: Session = Depends(get_db)) -> ResponseModel:
    from app.services.custom_tasks import is_task_used, get_task_parameters
    task = get_custom_task(db, name)
    if not task:
        return ResponseModel(code=404, msg=f"自定义任务 '{name}' 不存在")

    usage = is_task_used(task.name)
    params = get_task_parameters(task.code, task.name)

    task_dict = {
        "name": task.name,
        "category": task.category,
        "description": task.description,
        "code": task.code,
        "enabled": task.enabled,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "parameters": params,
        "is_used": usage["used"],
        "used_by_jobs": usage["jobs"]
    }

    return ResponseModel(data=task_dict, msg="获取自定义任务成功")


@router.post("/custom-tasks/", summary="创建自定义任务")
@api_error_handler
def create_custom_task_endpoint(
        request: CustomTaskCreate,
        db: Session = Depends(get_db)
) -> ResponseModel:
    task = create_custom_task(
        db,
        name=request.name,
        category=request.category,
        description=request.description,
        code=request.code
    )
    return ResponseModel(data=CustomTaskResponse.model_validate(task), msg="自定义任务创建成功")


@router.put("/custom-tasks/{name}", summary="更新自定义任务")
@api_error_handler
def update_custom_task_endpoint(
        name: str,
        request: CustomTaskUpdate,
        force: bool = Query(False, description="强制更新（即使任务正在被使用）"),
        db: Session = Depends(get_db)
) -> ResponseModel:
    from app.services.custom_tasks import is_task_used, get_task_parameters
    try:
        task = update_custom_task(
            db,
            name=name,
            category=request.category,
            description=request.description,
            code=request.code,
            enabled=request.enabled,
            force=force
        )
    except ValueError as e:
        return ResponseModel(code=400, msg=str(e))

    usage = is_task_used(task.name)
    params = get_task_parameters(task.code, task.name)

    task_dict = {
        "name": task.name,
        "category": task.category,
        "description": task.description,
        "code": task.code,
        "enabled": task.enabled,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "parameters": params,
        "is_used": usage["used"],
        "used_by_jobs": usage["jobs"]
    }

    return ResponseModel(data=task_dict, msg="自定义任务更新成功")


@router.delete("/custom-tasks/{name}", summary="删除自定义任务")
@api_error_handler
def delete_custom_task_endpoint(name: str, db: Session = Depends(get_db)) -> ResponseModel:
    try:
        deleted = delete_custom_task(db, name)
    except ValueError as e:
        return ResponseModel(code=400, msg=str(e))

    if not deleted:
        return ResponseModel(code=404, msg=f"自定义任务 '{name}' 不存在")
    return ResponseModel(data={"name": name}, msg="自定义任务已删除")


@router.get("/alerts/channels/", summary="获取告警渠道列表")
@api_error_handler
def list_alert_channels_endpoint(enabled_only: bool = Query(False, description="只返回已启用的渠道"), db: Session = Depends(get_db)) -> ResponseModel:
    channels = get_alert_channels(db, enabled_only=enabled_only)
    data = [AlertChannelResponse.model_validate(channel) for channel in channels]
    return ResponseModel(data=data, msg="获取告警渠道列表成功")


@router.post("/alerts/channels/", summary="创建告警渠道")
@api_error_handler
def create_alert_channel_endpoint(request: AlertChannelCreate, db: Session = Depends(get_db)) -> ResponseModel:
    existing = get_alert_channel_by_name(db, request.name)
    if existing:
        return ResponseModel(code=400, msg=f"渠道名称 '{request.name}' 已存在")
    
    channel = create_alert_channel(
        db,
        name=request.name,
        type=request.type,
        config=request.config,
        enabled=request.enabled
    )
    return ResponseModel(data=AlertChannelResponse.model_validate(channel), msg="告警渠道创建成功")


@router.get("/alerts/channels/{channel_id}", summary="获取告警渠道详情")
@api_error_handler
def get_alert_channel_endpoint(channel_id: int, db: Session = Depends(get_db)) -> ResponseModel:
    channel = get_alert_channel(db, channel_id)
    if not channel:
        return ResponseModel(code=404, msg=f"告警渠道 {channel_id} 不存在")
    return ResponseModel(data=AlertChannelResponse.model_validate(channel), msg="获取告警渠道成功")


@router.put("/alerts/channels/{channel_id}", summary="更新告警渠道")
@api_error_handler
def update_alert_channel_endpoint(channel_id: int, request: AlertChannelUpdate, db: Session = Depends(get_db)) -> ResponseModel:
    channel = update_alert_channel(
        db,
        channel_id=channel_id,
        name=request.name,
        config=request.config,
        enabled=request.enabled
    )
    if not channel:
        return ResponseModel(code=404, msg=f"告警渠道 {channel_id} 不存在")
    return ResponseModel(data=AlertChannelResponse.model_validate(channel), msg="告警渠道更新成功")


@router.delete("/alerts/channels/{channel_id}", summary="删除告警渠道")
@api_error_handler
def delete_alert_channel_endpoint(channel_id: int, db: Session = Depends(get_db)) -> ResponseModel:
    deleted = delete_alert_channel(db, channel_id)
    if not deleted:
        return ResponseModel(code=404, msg=f"告警渠道 {channel_id} 不存在")
    return ResponseModel(data={"channel_id": channel_id}, msg="告警渠道已删除")


@router.post("/alerts/channels/{channel_id}/test", summary="测试告警渠道")
@api_error_handler
def test_alert_channel_endpoint(channel_id: int, db: Session = Depends(get_db)) -> ResponseModel:
    from app.services.alert import test_alert_channel
    
    channel = get_alert_channel(db, channel_id)
    if not channel:
        return ResponseModel(code=404, msg=f"告警渠道 {channel_id} 不存在")
    
    result = test_alert_channel(channel)
    return ResponseModel(data=AlertTestResponse(**result), msg="测试完成")


@router.get("/alerts/rules/", summary="获取告警规则列表")
@api_error_handler
def list_alert_rules_endpoint(enabled_only: bool = Query(False, description="只返回已启用的规则"), db: Session = Depends(get_db)) -> ResponseModel:
    configs = get_alert_configs(db, enabled_only=enabled_only)
    
    data = []
    for config in configs:
        channel_ids = json.loads(config.channels) if isinstance(config.channels, str) else config.channels
        channels = get_alert_channels(db)
        channel_names = [c.name for c in channels if c.id in channel_ids]
        
        config_dict = {
            "id": config.id,
            "job_id": config.job_id,
            "rule_type": config.rule_type,
            "threshold": config.threshold,
            "channels": channel_ids,
            "channel_names": channel_names,
            "cooldown_minutes": config.cooldown_minutes,
            "enabled": config.enabled,
            "created_at": config.created_at,
            "updated_at": config.updated_at
        }
        data.append(AlertConfigResponse(**config_dict))
    
    return ResponseModel(data=data, msg="获取告警规则列表成功")


@router.post("/alerts/rules/", summary="创建告警规则")
@api_error_handler
def create_alert_rule_endpoint(request: AlertConfigCreate, db: Session = Depends(get_db)) -> ResponseModel:
    valid_rule_types = ["single_fail", "consecutive_fail", "timeout", "job_removed"]
    if request.rule_type not in valid_rule_types:
        return ResponseModel(code=400, msg=f"不支持的规则类型 '{request.rule_type}'")
    
    if request.rule_type in ["consecutive_fail", "timeout"] and request.threshold is None:
        default_threshold = 3 if request.rule_type == "consecutive_fail" else 60
        threshold = default_threshold
    else:
        threshold = request.threshold
    
    for channel_id in request.channels:
        channel = get_alert_channel(db, channel_id)
        if not channel:
            return ResponseModel(code=400, msg=f"告警渠道 {channel_id} 不存在")
    
    config = create_alert_config(
        db,
        rule_type=request.rule_type,
        channels=request.channels,
        job_id=request.job_id,
        threshold=threshold,
        cooldown_minutes=request.cooldown_minutes,
        enabled=request.enabled
    )
    
    channel_names = [c.name for c in get_alert_channels(db) if c.id in request.channels]
    config_dict = {
        "id": config.id,
        "job_id": config.job_id,
        "rule_type": config.rule_type,
        "threshold": config.threshold,
        "channels": request.channels,
        "channel_names": channel_names,
        "cooldown_minutes": config.cooldown_minutes,
        "enabled": config.enabled,
        "created_at": config.created_at,
        "updated_at": config.updated_at
    }
    
    return ResponseModel(data=AlertConfigResponse(**config_dict), msg="告警规则创建成功")


@router.get("/alerts/rules/{config_id}", summary="获取告警规则详情")
@api_error_handler
def get_alert_rule_endpoint(config_id: int, db: Session = Depends(get_db)) -> ResponseModel:
    config = get_alert_config(db, config_id)
    if not config:
        return ResponseModel(code=404, msg=f"告警规则 {config_id} 不存在")
    
    channel_ids = json.loads(config.channels) if isinstance(config.channels, str) else config.channels
    channels = get_alert_channels(db)
    channel_names = [c.name for c in channels if c.id in channel_ids]
    
    config_dict = {
        "id": config.id,
        "job_id": config.job_id,
        "rule_type": config.rule_type,
        "threshold": config.threshold,
        "channels": channel_ids,
        "channel_names": channel_names,
        "cooldown_minutes": config.cooldown_minutes,
        "enabled": config.enabled,
        "created_at": config.created_at,
        "updated_at": config.updated_at
    }
    
    return ResponseModel(data=AlertConfigResponse(**config_dict), msg="获取告警规则成功")


@router.put("/alerts/rules/{config_id}", summary="更新告警规则")
@api_error_handler
def update_alert_rule_endpoint(config_id: int, request: AlertConfigUpdate, db: Session = Depends(get_db)) -> ResponseModel:
    if request.rule_type:
        valid_rule_types = ["single_fail", "consecutive_fail", "timeout", "job_removed"]
        if request.rule_type not in valid_rule_types:
            return ResponseModel(code=400, msg=f"不支持的规则类型 '{request.rule_type}'")
    
    if request.channels:
        for channel_id in request.channels:
            channel = get_alert_channel(db, channel_id)
            if not channel:
                return ResponseModel(code=400, msg=f"告警渠道 {channel_id} 不存在")
    
    config = update_alert_config(
        db,
        config_id=config_id,
        job_id=request.job_id,
        rule_type=request.rule_type,
        threshold=request.threshold,
        channels=request.channels,
        cooldown_minutes=request.cooldown_minutes,
        enabled=request.enabled
    )
    
    if not config:
        return ResponseModel(code=404, msg=f"告警规则 {config_id} 不存在")
    
    channel_ids = json.loads(config.channels) if isinstance(config.channels, str) else config.channels
    channels = get_alert_channels(db)
    channel_names = [c.name for c in channels if c.id in channel_ids]
    
    config_dict = {
        "id": config.id,
        "job_id": config.job_id,
        "rule_type": config.rule_type,
        "threshold": config.threshold,
        "channels": channel_ids,
        "channel_names": channel_names,
        "cooldown_minutes": config.cooldown_minutes,
        "enabled": config.enabled,
        "created_at": config.created_at,
        "updated_at": config.updated_at
    }
    
    return ResponseModel(data=AlertConfigResponse(**config_dict), msg="告警规则更新成功")


@router.delete("/alerts/rules/{config_id}", summary="删除告警规则")
@api_error_handler
def delete_alert_rule_endpoint(config_id: int, db: Session = Depends(get_db)) -> ResponseModel:
    deleted = delete_alert_config(db, config_id)
    if not deleted:
        return ResponseModel(code=404, msg=f"告警规则 {config_id} 不存在")
    return ResponseModel(data={"config_id": config_id}, msg="告警规则已删除")


@router.get("/alerts/history/", summary="获取告警历史")
@api_error_handler
def list_alert_history_endpoint(
    job_id: Optional[str] = Query(None, description="任务ID模糊搜索"),
    status: Optional[bool] = Query(None, description="发送状态"),
    channel_type: Optional[str] = Query(None, description="渠道类型"),
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, le=100, description="每页数量"),
    db: Session = Depends(get_db)
) -> ResponseModel:
    result = list_alert_history(
        db,
        job_id=job_id,
        status=status,
        channel_type=channel_type,
        start_time=start_time,
        end_time=end_time,
        page=page,
        limit=limit
    )
    
    logs = [AlertHistoryResponse.model_validate(log) for log in result["logs"]]
    history_page = AlertHistoryPage(count=result["count"], logs=logs)
    
    return ResponseModel(data=history_page, msg="获取告警历史成功")
