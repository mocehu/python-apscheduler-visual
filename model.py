from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Union


class CronTrigger(BaseModel):
    day_of_week: Optional[int] = None  # '0-6', 0为周日.
    day: Optional[int] = None  # 1-31
    month: Optional[int] = None  # 1-12
    year: Optional[int] = None  # e.g., 2024
    hour: Optional[int] = None  # 0-23
    minute: Optional[int] = None  # 0-59
    second: Optional[int] = None  # 0-59


class IntervalTrigger(BaseModel):
    seconds: Optional[int] = None
    minutes: Optional[int] = None
    hours: Optional[int] = None
    days: Optional[int] = None
    weeks: Optional[int] = None


class DateTrigger(BaseModel):
    run_date: Optional[str] = None  # 格式: "2024-08-15T12:00:00"


class JobCreate(BaseModel):
    func: str  # 任务函数名
    trigger: str  # 触发器类型
    args: Optional[List] = []  # 任务位置参数
    kwargs: Optional[Dict] = {}  # 任务关键字参数
    job_id: str  # 任务ID

    # 触发器特有字段
    trigger_args: Optional[Union[CronTrigger, IntervalTrigger, DateTrigger]] = None


class JobResponse(BaseModel):
    id: str
    func: str
    next_run_time: str
    trigger: str
    args: List
    kwargs: dict
    status: str


class AvailableTask(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any]


# 日志查询接口
class LogEntry(BaseModel):
    id: int
    job_id: str
    status: str
    message: str
    timestamp: str


TYPE_MAP = {
    str: 'string',
    int: 'int',
    float: 'float',
    bool: 'bool',
    list: 'list',
    dict: 'dict',
    None: 'any'
}
