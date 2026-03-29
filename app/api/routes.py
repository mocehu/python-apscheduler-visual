import traceback
from datetime import datetime
from functools import wraps
from typing import Optional, Dict, Any, Callable

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_all_config, get_config, set_config, update_config_batch
from app.core.database import get_db, cleanup_old_logs, get_log_stats, clear_all_logs
from app.models.schemas import ResponseModel, AvailableTask, JobCreate, CronTrigger, IntervalTrigger, DateTrigger, \
    JobLogResponse, JobLogPage
from app.models.sql_model import JobLog, DEFAULT_CONFIG
from app.services.scheduler import add_job, remove_job, update_job, get_all_jobs, get_job_by_id, pause_job, resume_job, scheduler
from app.services.scheduler import update_auto_cleanup_schedule
from app.services.tasks import get_task_info, get_task_categories, get_task

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
                parameters=task_info["parameters"]
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
    
    add_job(
        func_name=job.func,
        trigger=job.trigger,
        args=job.args,
        kwargs=job.kwargs,
        job_id=job.job_id,
        name=job.name,
        **trigger_args
    )
    return ResponseModel(data={"job_id": job.job_id, "name": job.name}, msg="计划任务已添加")


@router.post("/update-job/", summary="修改计划任务")
@api_error_handler
def modify_job(job: JobCreate) -> ResponseModel:
    job_obj = scheduler.get_job(job_id=job.job_id)
    if not job_obj:
        return ResponseModel(code=404, msg=f"计划任务 {job.job_id} 不存在")
    
    task_func = get_task(job.func)
    if not task_func:
        return ResponseModel(code=404, msg=f"任务函数 '{job.func}' 未找到")
    
    trigger_args = _validate_trigger(job)
    
    update_job(
        func=job.func,
        job_id=job.job_id,
        trigger=job.trigger,
        trigger_args=trigger_args,
        args=job.args,
        kwargs=job.kwargs,
        name=job.name
    )
    return ResponseModel(data={"job_id": job.job_id, "name": job.name}, msg="任务已更新")


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
    return ResponseModel(data=result, msg=f"日志清理完成，共删除 {result['deleted_by_age'] + result['deleted_by_count']} 条")


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