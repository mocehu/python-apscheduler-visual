# api.py
import traceback
from datetime import datetime
from functools import wraps
from typing import Optional, Dict, Any, Callable

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from datebase import get_db
from resp_model import ResponseModel, AvailableTask, JobCreate, CronTrigger, IntervalTrigger, DateTrigger, \
    JobLogResponse, JobLogPage
from scheduler import add_job, remove_job, update_job, get_all_jobs, pause_job, resume_job, scheduler
from sql_model import JobLog
from tasks import get_task_info, get_task_categories, get_task

router = APIRouter()


def api_error_handler(func: Callable) -> Callable:
    """API错误处理装饰器，统一处理异常"""

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
    """立即执行任务"""
    job = scheduler.get_job(job_id=job_id)
    if not job:
        return ResponseModel(code=404, msg=f"任务 {job_id} 不存在")

    # 设置任务立即执行
    job = scheduler.modify_job(job_id=job_id, next_run_time=datetime.now())

    return ResponseModel(data=job.id, msg=f"任务 {job_id} 已安排立即执行")


@router.get("/available-tasks/", summary="可用任务函数列表")
@api_error_handler
def list_available_tasks(category: Optional[str] = None) -> ResponseModel:
    """可用任务函数列表"""
    # 获取任务信息
    all_tasks = get_task_info()

    # 如果指定了分类，过滤出该分类的任务
    if category:
        all_tasks = [task for task in all_tasks if task["category"] == category]

    # 转换为AvailableTask模型
    available_tasks = []
    for task_info in all_tasks:
        available_tasks.append(
            AvailableTask(
                name=task_info["name"],
                description=task_info["description"],
                parameters=task_info["parameters"],
                category=task_info["category"]
            )
        )

    # 分类汇总
    categories = get_task_categories()

    return ResponseModel(
        data={
            "tasks": available_tasks,
            "categories": categories
        },
        msg="获取可用任务列表成功"
    )


def normalize_cron_args(data: dict) -> dict:
    cleaned = {}
    for k, v in data.items():
        if k == "day_of_week" and not (0 <= v <= 6):
            continue
        if k == "week" and not (1 <= v <= 53):
            continue
        if k == "year" and v < 1970:
            continue
        if k == "month" and not (1 <= v <= 12):
            continue
        if k == "day" and not (1 <= v <= 31):
            continue
        if k == "hour" and not (0 <= v <= 23):
            continue
        if k in ("minute", "second") and not (0 <= v <= 59):
            continue
        cleaned[k] = v
    return cleaned


def _validate_trigger(job: JobCreate) -> Dict[str, Any]:
    """验证触发器参数"""
    # 验证触发器类型及其参数
    trigger_args = job.trigger_args or {}
    if job.trigger == "cron":
        model = CronTrigger(**trigger_args)
        data = model.dict()

        # 这里加转换：处理特殊字段需要*的问题
        valid_args = normalize_cron_args(data)

        return valid_args
    elif job.trigger == "interval":
        model = IntervalTrigger(**trigger_args)
    elif job.trigger == "date":
        model = DateTrigger(**trigger_args)
    else:
        raise ValueError(f"不支持的触发器类型 '{job.trigger}'")

    return {k: v for k, v in model.dict().items() if v is not None}


@router.post("/add-job/", summary="新建任务")
@api_error_handler
def create_job(job: JobCreate) -> ResponseModel:
    """新建任务"""
    # 验证任务是否存在
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
        **trigger_args
    )
    return ResponseModel(data=job.job_id, msg="任务已添加")


@router.post("/update-job/", summary="修改任务")
@api_error_handler
def modify_job(job: JobCreate) -> ResponseModel:
    """修改任务"""
    # 检查任务是否存在
    job_obj = scheduler.get_job(job_id=job.job_id)
    if not job_obj:
        return ResponseModel(code=404, msg=f"任务 {job.job_id} 不存在")

    # 检查任务函数是否存在
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
        kwargs=job.kwargs
    )
    return ResponseModel(data=job.job_id, msg="任务已更新")


@router.get("/pause-job/{job_id}", summary="暂停任务")
@api_error_handler
def pause_job_endpoint(job_id: str) -> ResponseModel:
    """暂停任务"""
    # 检查任务是否存在
    job = scheduler.get_job(job_id=job_id)
    if not job:
        return ResponseModel(code=404, msg=f"任务 {job_id} 不存在")

    pause_job(job_id)
    return ResponseModel(data=job_id, msg=f"任务 {job_id} 已暂停")


@router.get("/resume-job/{job_id}", summary="恢复（被暂停的）任务")
@api_error_handler
def resume_job_endpoint(job_id: str) -> ResponseModel:
    """恢复（被暂停的）任务"""
    # 检查任务是否存在
    job = scheduler.get_job(job_id=job_id)
    if not job:
        return ResponseModel(code=404, msg=f"任务 {job_id} 不存在")

    resume_job(job_id)
    return ResponseModel(data=job_id, msg=f"任务 {job_id} 已恢复")


@router.get("/remove-job/{job_id}", summary="删除任务")
@api_error_handler
def delete_job(job_id: str) -> ResponseModel:
    """删除任务"""
    # 检查任务是否存在
    job = scheduler.get_job(job_id=job_id)
    if not job:
        return ResponseModel(code=404, msg=f"任务 {job_id} 不存在")

    remove_job(job_id)
    return ResponseModel(data=job_id, msg="任务已移除")


@router.get("/jobs/", summary="任务列表")
@api_error_handler
def list_jobs() -> ResponseModel:
    """任务列表"""
    jobs = get_all_jobs()
    return ResponseModel(data=jobs, msg="获取任务列表成功")


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
    """任务日志查询"""
    query = db.query(JobLog)

    # 应用过滤条件
    if job_id:
        query = query.filter(JobLog.job_id.ilike(f"%{job_id}%"))
    if status is not None:
        query = query.filter(JobLog.status == status)
    if start_time:
        query = query.filter(JobLog.timestamp >= start_time)
    if end_time:
        query = query.filter(JobLog.timestamp <= end_time)

    # 获取总数
    total_count = query.count()

    # 分页
    offset = (page - 1) * limit
    db_logs = query.order_by(JobLog.timestamp.desc()).offset(offset).limit(limit).all()

    # 将数据库模型转换为响应模型
    logs = [JobLogResponse.model_validate(log) for log in db_logs]

    log_page = JobLogPage(count=total_count, logs=logs)
    return ResponseModel(data=log_page, msg="获取日志成功")


@router.get("/task-categories/", summary="获取任务分类")
@api_error_handler
def list_task_categories() -> ResponseModel:
    """获取所有任务分类"""
    categories = get_task_categories()
    return ResponseModel(data=categories, msg="获取任务分类成功")


@router.get("/task-info/{task_name}", summary="获取任务详情")
@api_error_handler
def get_task_details(task_name: str) -> ResponseModel:
    """获取特定任务的详细信息"""
    task_info = get_task_info(task_name)
    if not task_info:
        return ResponseModel(code=404, msg=f"任务 {task_name} 不存在")

    return ResponseModel(data=task_info, msg="获取任务详情成功")
