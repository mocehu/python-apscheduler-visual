import logging
import time
from typing import Any, Dict, Optional
from typing import Any, Dict, Optional

from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_SUBMITTED
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from app.core.conf import DATABASE_URL
from app.core.database import _session_factory, get_config_bool, get_config_int
from app.models.sql_model import JobLog

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

jobstores = {
    'default': SQLAlchemyJobStore(url=DATABASE_URL)
}
executors = {
    'default': ThreadPoolExecutor(20)
}
job_defaults = {
    'coalesce': True,
    'max_instances': 3,
    'misfire_grace_time': None
}

scheduler = BackgroundScheduler(jobstores=jobstores, executors=executors, job_defaults=job_defaults)


def log_to_db(job_id, status, message, duration=None, output=None):
    try:
        db = _session_factory()
        new_log = JobLog(
            job_id=job_id,
            status=status,
            message=message,
            duration=duration,
            output=output
        )
        db.add(new_log)
        db.commit()
    except Exception as e:
        logger.error(f"日志记录失败: {e}")
    finally:
        try:
            db.close()
        except Exception:
            pass


task_start_times = {}


def job_listener(event):
    job_id = event.job_id

    if event.code == EVENT_JOB_SUBMITTED:
        task_start_times[job_id] = int(time.time() * 1000)

    elif event.code in (EVENT_JOB_EXECUTED, EVENT_JOB_ERROR):
        end_time = int(time.time() * 1000)
        start_time = task_start_times.pop(job_id, end_time)
        execution_duration = end_time - start_time

        if event.exception:
            log_to_db(job_id, False, str(event.exception), execution_duration, None)
            logger.error(f"任务 {job_id} 执行失败: {event.exception}")
            
            from app.services.alert import check_and_alert
            check_and_alert(job_id, False, execution_duration, str(event.exception))
        else:
            if hasattr(event, 'retval'):
                result = event.retval
                if isinstance(result, dict):
                    duration = result.get('elapsed_time', execution_duration)
                    output = result.get('output', '')
                    status = result.get('status', True)
                    error = result.get('error', None)
                    task_result = result.get('result', None)
                    
                    if output and task_result:
                        output = f"{output}\n结果: {task_result}"
                    elif task_result:
                        output = f"结果: {task_result}"
                    
                    if status:
                        log_to_db(job_id, True, '任务成功执行', duration, output)
                        logger.info(f"任务 {job_id} 执行成功: {output}. 执行时长: {duration}毫秒")
                        
                        from app.services.alert import check_and_alert, reset_fail_count
                        reset_fail_count(job_id)
                        check_and_alert(job_id, True, duration, None)
                    else:
                        log_to_db(job_id, False, error or '任务执行失败', duration, output)
                        logger.error(f"任务 {job_id} 执行失败: {error or '未知错误'}. 执行时长: {duration}毫秒")
                        
                        from app.services.alert import check_and_alert
                        check_and_alert(job_id, False, duration, error)
                elif isinstance(result, tuple) and len(result) == 2:
                    duration, output = result
                    log_to_db(job_id, True, '任务成功执行', duration, output)
                    logger.info(f"任务 {job_id} 执行成功: {output}. 执行时长: {duration}毫秒")
                    
                    from app.services.alert import check_and_alert, reset_fail_count
                    reset_fail_count(job_id)
                    check_and_alert(job_id, True, duration, None)
                else:
                    log_to_db(job_id, True, '任务成功执行', execution_duration, str(result))
                    logger.info(f"任务 {job_id} 执行成功: {result}. 执行时长: {execution_duration}毫秒")
                    
                    from app.services.alert import check_and_alert, reset_fail_count
                    reset_fail_count(job_id)
                    check_and_alert(job_id, True, execution_duration, None)
            else:
                log_to_db(job_id, True, '任务成功执行', execution_duration, '无输出内容')
                logger.info(f"任务 {job_id} 执行成功，无返回值. 执行时长: {execution_duration}毫秒")
                
                from app.services.alert import check_and_alert, reset_fail_count
                reset_fail_count(job_id)
                check_and_alert(job_id, True, execution_duration, None)


def start_scheduler():
    import app.services.tasks
    scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    scheduler.start()
    logger.info("定时任务已启动")
    
    _cleanup_invalid_jobs()
    setup_auto_cleanup()
    _load_custom_tasks()


def _load_custom_tasks():
    from app.services.custom_tasks import load_custom_tasks
    
    db = _session_factory()
    try:
        result = load_custom_tasks(db)
        if result["loaded"]:
            logger.info(f"已加载 {len(result['loaded'])} 个自定义任务")
        if result["errors"]:
            logger.warning(f"加载自定义任务出错: {result['errors']}")
    except Exception as e:
        logger.warning(f"加载自定义任务时出错: {e}")
    finally:
        db.close()


def _cleanup_invalid_jobs():
    try:
        jobs = scheduler.get_jobs()
        for job in jobs:
            try:
                _ = job.func
            except (LookupError, AttributeError):
                logger.warning(f"发现无效任务引用: {job.id}, 正在移除...")
                
                from app.services.alert import check_and_alert
                check_and_alert(job.id, False, None, "任务不存在或已被移除", job_exists=False)
                
                try:
                    scheduler.remove_job(job.id)
                except Exception as e:
                    logger.error(f"移除任务 {job.id} 失败: {e}")
    except Exception as e:
        logger.warning(f"清理无效任务时出错: {e}")


def setup_auto_cleanup():
    from app.services.tasks import get_task
    
    db = _session_factory()
    try:
        auto_cleanup = get_config_bool(db, "log_auto_cleanup", True)
        cleanup_hour = get_config_int(db, "log_cleanup_hour", 3)
    finally:
        db.close()
    
    cleanup_job_id = "auto_cleanup_logs"
    
    try:
        existing_job = scheduler.get_job(cleanup_job_id)
    except LookupError:
        try:
            scheduler.remove_job(cleanup_job_id)
            logger.info(f"已移除无效任务: {cleanup_job_id}")
        except Exception:
            pass
        existing_job = None
    
    if not auto_cleanup:
        if existing_job:
            scheduler.remove_job(cleanup_job_id)
            logger.info("已移除自动日志清理任务")
        return
    
    task_func = get_task("auto_cleanup_logs")
    if not task_func:
        logger.warning("找不到 auto_cleanup_logs 任务函数，跳过自动清理设置")
        return
    
    trigger = CronTrigger(hour=cleanup_hour, minute=0)
    scheduler.add_job(
        task_func,
        trigger,
        id=cleanup_job_id,
        replace_existing=True
    )
    logger.info(f"已添加自动日志清理任务: 每天 {cleanup_hour}:00 执行")


def update_auto_cleanup_schedule():
    setup_auto_cleanup()


def stop_scheduler():
    scheduler.shutdown()


def add_job(func_name, trigger, args=None, kwargs=None, job_id=None, name=None, **trigger_args):
    from app.services.tasks import get_task, custom_task_dispatcher
    from app.services.custom_tasks import get_custom_task as get_custom_task_from_db
    
    task_func = get_task(func_name)
    if not task_func:
        raise ValueError(f"任务函数 '{func_name}' 找不到")
    
    if job_id and scheduler.get_job(job_id):
        raise ValueError(f"任务 ID '{job_id}' 已存在")

    if trigger == "cron":
        aps_trigger = CronTrigger(**trigger_args)
    elif trigger == "interval":
        aps_trigger = IntervalTrigger(**trigger_args)
    elif trigger == "date":
        aps_trigger = DateTrigger(**trigger_args)
    else:
        raise ValueError(f"不支持的触发器类型 '{trigger}'")

    # 检查是否是自定义任务
    is_custom = hasattr(task_func, 'code') or (hasattr(task_func, 'task_name') and hasattr(task_func, 'task_category'))
    
    if is_custom:
        # 自定义任务使用调度器，确保可以序列化
        job = scheduler.add_job(
            custom_task_dispatcher,
            aps_trigger,
            args=[func_name] + (args or []),
            kwargs=kwargs or {},
            id=job_id,
            name=name,
        )
    else:
        # 内置任务直接使用函数
        job = scheduler.add_job(
            task_func,
            aps_trigger,
            args=args,
            kwargs=kwargs,
            id=job_id,
            name=name,
        )
    
    actual_job_id = job.id
    logger.info(f'添加任务: {actual_job_id} ({name or "无名称"}) [自定义任务: {is_custom}]')
    return actual_job_id


def remove_job(job_id):
    scheduler.remove_job(job_id)
    logger.info(f'移除任务: {job_id}')


def update_job(func: str, job_id: str, trigger: str, trigger_args: dict, args: list, kwargs: dict, name: str = None):
    from app.services.tasks import get_task, custom_task_dispatcher
    
    task_func = get_task(func)
    if not task_func:
        raise ValueError(f"任务函数 '{func}' 找不到")

    job = scheduler.get_job(job_id)
    if not job:
        raise ValueError(f"任务 {job_id} 不存在")

    is_paused = job.next_run_time is None

    if trigger == 'interval':
        valid_args = {key: trigger_args[key] for key in ['weeks', 'days', 'hours', 'minutes', 'seconds'] if
                      key in trigger_args}
        trigger_obj = IntervalTrigger(**valid_args)
    elif trigger == 'cron':
        valid_args = {key: trigger_args[key] for key in
                      ['year', 'month', 'day', 'week', 'day_of_week', 'hour', 'minute', 'second'] if
                      key in trigger_args}
        trigger_obj = CronTrigger(**valid_args)
    elif trigger == 'date':
        trigger_obj = DateTrigger(run_date=trigger_args.get('run_date'))
    else:
        raise ValueError(f"不支持的触发器类型: {trigger}")

    # 检查是否是自定义任务
    is_custom = hasattr(task_func, 'code') or (hasattr(task_func, 'task_name') and hasattr(task_func, 'task_category'))
    
    if is_custom:
        modify_kwargs = {"args": [func] + (args or []), "kwargs": kwargs or {}, "func": custom_task_dispatcher}
    else:
        modify_kwargs = {"args": args, "kwargs": kwargs, "func": task_func}
    
    if name is not None:
        modify_kwargs["name"] = name
    job.modify(**modify_kwargs)
    scheduler.reschedule_job(job_id, trigger=trigger_obj)
    
    if is_paused:
        scheduler.pause_job(job_id)
    
    logger.info(f'更新任务: {job_id} [自定义任务: {is_custom}]')


def pause_job(job_id):
    scheduler.pause_job(job_id)
    logger.info(f'暂停任务: {job_id}')


def resume_job(job_id):
    scheduler.resume_job(job_id)
    logger.info(f'恢复任务: {job_id}')


def run_job(job_id):
    job = scheduler.get_job(job_id)
    if not job:
        raise ValueError(f"任务 {job_id} 不存在")

    result = job.func(*job.args, **job.kwargs)
    
    return result


def get_all_jobs():
    try:
        jobs = scheduler.get_jobs()
    except LookupError as e:
        logger.warning(f"加载任务时发现无效引用: {e}")
        jobs = []
    except Exception as e:
        logger.error(f"获取任务列表失败: {e}")
        return []
    
    job_info = []
    for job in jobs:
        try:
            next_run = getattr(job, 'next_run_time', None)
            
            # 处理自定义任务的 func 名称
            func_name = job.func.__name__ if hasattr(job.func, '__name__') else str(job.func)
            args = list(job.args) if job.args else []
            kwargs = dict(job.kwargs) if job.kwargs else {}
            
            # 如果是 custom_task_dispatcher，从 args[0] 获取实际函数名
            if func_name == 'custom_task_dispatcher' and args:
                actual_func_name = args[0]
                args = args[1:]  # 剩余的才是实际参数
            else:
                actual_func_name = func_name
            
            job_info.append({
                "id": job.id,
                "name": job.name,
                "func": actual_func_name,
                "next_run_time": str(next_run) if next_run else None,
                "trigger": str(job.trigger),
                "args": args,
                "kwargs": kwargs,
                "status": "已暂停" if next_run is None else "工作中"
            })
        except Exception as e:
            logger.warning(f"解析任务 {job.id} 信息失败: {e}")
            job_info.append({
                "id": job.id,
                "name": getattr(job, 'name', None),
                "func": "unknown",
                "next_run_time": None,
                "trigger": str(getattr(job, 'trigger', 'unknown')),
                "args": [],
                "kwargs": {},
                "status": "异常"
            })
    return job_info


def get_job_by_id(job_id: str) -> Optional[Dict[str, Any]]:
    """获取单个任务详情"""
    try:
        job = scheduler.get_job(job_id)
    except LookupError:
        return None
    
    if not job:
        return None
    
    next_run = job.next_run_time
    
    # 处理自定义任务的 func 名称
    func_name = job.func.__name__ if hasattr(job.func, '__name__') else str(job.func)
    args = list(job.args) if job.args else []
    kwargs = dict(job.kwargs) if job.kwargs else {}
    
    # 如果是 custom_task_dispatcher，从 args[0] 获取实际函数名
    if func_name == 'custom_task_dispatcher' and args:
        actual_func_name = args[0]
        args = args[1:]  # 剩余的才是实际参数
    else:
        actual_func_name = func_name
    
    return {
        "id": job.id,
        "name": job.name,
        "func": actual_func_name,
        "next_run_time": str(next_run) if next_run else None,
        "trigger": str(job.trigger),
        "args": args,
        "kwargs": kwargs,
        "status": "已暂停" if next_run is None else "工作中"
    }
