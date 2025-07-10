from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Union
from datetime import datetime


class ResponseModel(BaseModel):
    """统一响应模型"""
    code: int = 200  # 状态码
    msg: str = "成功"  # 响应消息
    data: Any = None  # 响应数据


class CronTrigger(BaseModel):
    day_of_week: Optional[int] = None  # '0-6', 0为周日.
    day: Optional[int] = 1  # 1-31
    month: Optional[int] = 1  # 1-12
    year: Optional[int] = None  # e.g., 2024
    hour: Optional[int] = 0  # 0-23
    minute: Optional[int] = 0  # 0-59
    second: Optional[int] = 0  # 0-59


class IntervalTrigger(BaseModel):
    seconds: Optional[int] = 0
    minutes: Optional[int] = 0
    hours: Optional[int] = 0
    days: Optional[int] = 0
    weeks: Optional[int] = 0


class DateTrigger(BaseModel):
    run_date: Optional[str] = None  # 格式: "2024-08-15T12:00:00"


class JobCreate(BaseModel):
    func: str  # 任务函数名
    trigger: str  # 触发器类型
    args: Optional[List] = []  # 任务位置参数
    kwargs: Optional[Dict] = {}  # 任务关键字参数
    job_id: str  # 任务ID

    # 触发器特有字段
    trigger_args: Optional[Dict[str, Any]] = None


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


class JobLogResponse(BaseModel):
    """任务日志响应模型"""
    id: int
    job_id: str
    status: bool
    message: str
    duration: Optional[float] = None
    output: Optional[str] = None
    timestamp: datetime
    
    model_config = {
        "from_attributes": True  # 启用ORM模式，允许从ORM对象创建Pydantic模型
    }


class JobLogPage(BaseModel):
    """任务日志分页响应"""
    count: int
    logs: List[JobLogResponse]


TYPE_MAP = {
    str: 'string',
    int: 'int',
    float: 'float',
    bool: 'bool',
    list: 'list',
    dict: 'dict',
    None: 'any'
}
