# api.py
import inspect
import traceback
from datetime import datetime
from typing import List

from fastapi import APIRouter, HTTPException, Body, Depends, Query

from datebase import get_db
from resp_model import *
from scheduler import add_job, remove_job, update_job, get_all_jobs, pause_job, resume_job, run_job
from sql_model import JobLog
from tasks import get_tasks
from sqlalchemy.orm import Session

router = APIRouter()


@router.post("/run-job-now/", summary="立即执行")
def run_job_now(job_id: str):
    try:
        run_job(job_id)
        return {"message": f"任务 {job_id} 已立即执行"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/available-tasks/", response_model=List[AvailableTask], summary="可用任务函数列表")
def list_available_tasks() -> List[AvailableTask]:
    """
    可用任务函数列表
    :return: 包含任务函数名称、描述和参数信息的列表
    """
    try:
        tasks = get_tasks()
        available_tasks = []

        for task_name, task in tasks.items():
            # 获取函数签名
            sig = inspect.signature(task)
            params = sig.parameters

            # 提取参数信息
            param_info = {
                param_name: {
                    "name": param_name,
                    "type": TYPE_MAP.get(param.annotation, '未知'),
                    "default": str(param.default) if param.default is not inspect.Parameter.empty else ''
                }
                for param_name, param in params.items()
            }

            available_tasks.append(
                AvailableTask(
                    name=task_name,
                    description=task.__doc__ or "无方法文档",
                    parameters=param_info
                )
            )

        return available_tasks
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/add-job/", summary="新建任务")
def create_job(job: JobCreate):
    """
    新建任务
    :param job: 任务创建信息
    :return: 任务添加结果
    """
    try:
        tasks = get_tasks()  # 获取所有任务函数
        if job.func not in tasks:
            raise ValueError(f"方法 '{job.func}' 未找到")

        # 处理触发器参数
        trigger_args = job.trigger_args or {}

        # 校验触发器类型及其参数
        if job.trigger == "cron":
            # Cron 触发器
            if not isinstance(trigger_args, CronTrigger):
                raise ValueError("Cron 触发器参数错误")
            trigger_args = {k: v for k, v in trigger_args.dict().items() if v is not None}
        elif job.trigger == "interval":
            # Interval 触发器
            if not isinstance(trigger_args, IntervalTrigger):
                raise ValueError("Interval 触发器参数错误")
            trigger_args = {k: v for k, v in trigger_args.dict().items() if v is not None}
        elif job.trigger == "date":
            # Date 触发器
            if not isinstance(trigger_args, DateTrigger):
                raise ValueError("Date 触发器参数错误")
            trigger_args = {k: v for k, v in trigger_args.dict().items() if v is not None}
        else:
            raise ValueError(f"不支持的触发器类型 '{job.trigger}'")

        add_job(
            func_name=job.func,
            trigger=job.trigger,
            args=job.args,
            kwargs=job.kwargs,
            job_id=job.job_id,
            **trigger_args
        )
        return {"message": "任务已添加"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/update-job/", summary="修改任务")
def modify_job(job: JobCreate):
    """
    修改任务
    :param job: 任务更新信息
    :return: 更新成功的消息
    """
    try:
        update_job(
            func=job.func,
            job_id=job.job_id,
            trigger=job.trigger,
            trigger_args=job.trigger_args.dict() if job.trigger_args else {},
            args=job.args,
            kwargs=job.kwargs
        )
        return {"message": "任务已更新"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/pause-job/{job_id}", summary="暂停任务")
def pause_job_api(job_id: str):
    """
    暂停任务
    :param job_id:
    :return:
    """
    try:
        pause_job(job_id)
        return {"message": f"任务 {job_id} 已暂停"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/resume-job/{job_id}", summary="恢复（被暂停的）任务")
def resume_job_api(job_id: str):
    """
    恢复（被暂停的）任务
    :param job_id:
    :return:
    """
    try:
        resume_job(job_id)
        return {"message": f" {job_id} 已恢复"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/remove-job/{job_id}", summary="删除任务")
def delete_job(job_id: str):
    """
    删除任务
    :param job_id:
    :return:
    """
    try:
        remove_job(job_id)
        return {"message": "任务已移除"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/jobs/", response_model=List[JobResponse], summary="任务列表")
def list_jobs():
    """
    任务列表
    :return:
    """
    try:
        jobs = get_all_jobs()
        return jobs
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/logs/", summary="任务日志")
def get_logs(
        job_id: Optional[str] = Query(None, description="任务ID进行模糊查找"),
        status: Optional[bool] = Query(None, description="日志状态进行筛选，例如True或False"),
        start_time: Optional[datetime] = Query(None, description="起始时间YYYY-MM-DDTHH:MM:SS"),
        end_time: Optional[datetime] = Query(None, description="结束时间"),
        page: int = Query(1, ge=1, description="页数，从1开始"),
        limit: int = Query(10, le=100, description="每页返回的日志数量"),
        db: Session = Depends(get_db)
):
    try:
        query = db.query(JobLog)

        # 根据任务ID进行模糊查询
        if job_id:
            query = query.filter(JobLog.job_id.ilike(f"%{job_id}%"))

        # 根据状态进行筛选
        if status is not None:
            query = query.filter(JobLog.status == status)

        # 根据时间范围进行筛选
        if start_time:
            query = query.filter(JobLog.timestamp >= start_time)
        if end_time:
            query = query.filter(JobLog.timestamp <= end_time)

        # 获取总数
        total_count = query.count()

        # 计算偏移量
        offset = (page - 1) * limit

        # 应用分页
        logs = query.order_by(JobLog.timestamp.desc()).offset(offset).limit(limit).all()

        # 返回数据和总数
        return {"count": total_count, "logs": logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

