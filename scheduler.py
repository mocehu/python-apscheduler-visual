# scheduler.py
import time

from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_SUBMITTED
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
import logging
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from conf import DATABASE_URL
from datebase import get_db
from sql_model import JobLog

# Log configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Scheduler configuration
jobstores = {
    'default': SQLAlchemyJobStore(url=DATABASE_URL)
}
executors = {
    'default': ThreadPoolExecutor(20)
}
job_defaults = {
    'coalesce': True,  # 是否合并错过的任务
    'max_instances': 3,
    'misfire_grace_time': None  # 错过任务的宽限时间（秒）
}

scheduler = BackgroundScheduler(jobstores=jobstores, executors=executors, job_defaults=job_defaults)


def log_to_db(job_id, status, message, duration=None, output=None):
    try:
        db = next(get_db())  # 获取数据库会话
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


# 监听任务执行事件
# 全局字典来跟踪任务开始时间
task_start_times = {}


def job_listener(event):
    job_id = event.job_id

    if event.code == EVENT_JOB_SUBMITTED:
        # 任务开始执行时记录当前时间（以毫秒为单位）
        task_start_times[job_id] = int(time.time() * 1000)

    elif event.code in (EVENT_JOB_EXECUTED, EVENT_JOB_ERROR):
        end_time = int(time.time() * 1000)
        start_time = task_start_times.pop(job_id, end_time)
        execution_duration = end_time - start_time  # 执行时长以毫秒为单位

        if event.exception:
            # 记录任务执行失败日志
            log_to_db(job_id, False, str(event.exception), execution_duration, None)
            logger.error(f"任务 {job_id} 执行失败: {event.exception}")
        else:
            # 获取任务的返回值，处理新旧两种返回格式
            if hasattr(event, 'retval'):
                result = event.retval
                # 检查返回值类型
                if isinstance(result, dict):
                    # 新格式返回值：字典格式
                    duration = result.get('elapsed_time', execution_duration)
                    output = result.get('output', '')
                    status = result.get('status', True)
                    error = result.get('error', None)
                    task_result = result.get('result', None)
                    
                    # 合并输出和结果
                    if output and task_result:
                        output = f"{output}\n结果: {task_result}"
                    elif task_result:
                        output = f"结果: {task_result}"
                    
                    # 根据状态记录日志
                    if status:
                        log_to_db(job_id, True, '任务成功执行', duration, output)
                        logger.info(f"任务 {job_id} 执行成功: {output}. 执行时长: {duration}毫秒")
                    else:
                        log_to_db(job_id, False, error or '任务执行失败', duration, output)
                        logger.error(f"任务 {job_id} 执行失败: {error or '未知错误'}. 执行时长: {duration}毫秒")
                elif isinstance(result, tuple) and len(result) == 2:
                    # 旧格式返回值：(duration, output)元组
                    duration, output = result
                    log_to_db(job_id, True, '任务成功执行', duration, output)
                    logger.info(f"任务 {job_id} 执行成功: {output}. 执行时长: {duration}毫秒")
                else:
                    # 其他类型的返回值，直接当作输出
                    log_to_db(job_id, True, '任务成功执行', execution_duration, str(result))
                    logger.info(f"任务 {job_id} 执行成功: {result}. 执行时长: {execution_duration}毫秒")
            else:
                # 无返回值
                log_to_db(job_id, True, '任务成功执行', execution_duration, '无输出内容')
                logger.info(f"任务 {job_id} 执行成功，无返回值. 执行时长: {execution_duration}毫秒")


def start_scheduler():
    scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    scheduler.start()
    logger.info("定时任务已启动")


def stop_scheduler():
    scheduler.shutdown()


def add_job(func_name, trigger, args=None, kwargs=None, job_id=None, **trigger_args):
    from tasks import get_task
    
    task_func = get_task(func_name)
    if not task_func:
        raise ValueError(f"任务函数 '{func_name}' 找不到")
    
    if scheduler.get_job(job_id):
        raise ValueError(f"任务 ID '{job_id}' 已存在")

    # 设置触发器
    if trigger == "cron":
        # 设置 Cron 触发器
        aps_trigger = CronTrigger(**trigger_args)
    elif trigger == "interval":
        # 设置 Interval 触发器
        aps_trigger = IntervalTrigger(**trigger_args)
    elif trigger == "date":
        # 设置 Date 触发器
        aps_trigger = DateTrigger(**trigger_args)
    else:
        raise ValueError(f"不支持的触发器类型 '{trigger}'")

    # 添加任务
    scheduler.add_job(
        task_func,
        aps_trigger,
        args=args,
        kwargs=kwargs,
        id=job_id,
        **trigger_args
    )
    logger.info(f'添加任务: {job_id}')


def remove_job(job_id):
    scheduler.remove_job(job_id)
    logger.info(f'移除任务: {job_id}')


def update_job(func: str, job_id: str, trigger: str, trigger_args: dict, args: list, kwargs: dict):
    """
    更新任务的触发器和参数
    :param job_id: 任务ID
    :param trigger: 触发器类型
    :param trigger_args: 触发器参数
    :param args: 任务参数
    :param kwargs: 任务关键字参数
    """
    from tasks import get_task
    
    task_func = get_task(func)
    if not task_func:
        raise ValueError(f"任务函数 '{func}' 找不到")

    job = scheduler.get_job(job_id)
    if not job:
        raise ValueError(f"任务 {job_id} 不存在")

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

    # 修改任务
    job.modify(args=args, kwargs=kwargs, func=task_func)
    scheduler.reschedule_job(job_id, trigger=trigger_obj)
    logger.info(f'更新任务: {job_id}')


def pause_job(job_id):
    scheduler.pause_job(job_id)
    logger.info(f'暂停任务: {job_id}')


def resume_job(job_id):
    scheduler.resume_job(job_id)
    logger.info(f'恢复任务: {job_id}')


def run_job(job_id):
    # 获取任务
    job = scheduler.get_job(job_id)
    if not job:
        raise ValueError(f"任务 {job_id} 不存在")

    # 立即运行任务
    result = job.func(*job.args, **job.kwargs)
    
    # 返回任务执行结果
    return result


def get_all_jobs():
    jobs = scheduler.get_jobs()
    job_info = []
    for job in jobs:
        job_info.append({
            "id": job.id,
            "func": job.func.__name__,
            "next_run_time": str(job.next_run_time),
            "trigger": str(job.trigger),
            "args": job.args,
            "kwargs": job.kwargs,
            "status": "已暂停" if job.next_run_time is None else "工作中"
        })
    return job_info
