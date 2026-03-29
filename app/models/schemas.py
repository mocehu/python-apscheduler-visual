from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Union
from datetime import datetime


class ResponseModel(BaseModel):
    code: int = 200
    msg: str = "成功"
    data: Any = None


class CronTrigger(BaseModel):
    day_of_week: Optional[int] = None
    day: Optional[int] = 1
    month: Optional[int] = 1
    year: Optional[int] = None
    hour: Optional[int] = 0
    minute: Optional[int] = 0
    second: Optional[int] = 0


class IntervalTrigger(BaseModel):
    seconds: Optional[int] = 0
    minutes: Optional[int] = 0
    hours: Optional[int] = 0
    days: Optional[int] = 0
    weeks: Optional[int] = 0


class DateTrigger(BaseModel):
    run_date: Optional[str] = None


class JobCreate(BaseModel):
    func: str
    trigger: str
    args: Optional[List] = []
    kwargs: Optional[Dict] = {}
    job_id: str
    name: Optional[str] = None
    trigger_args: Optional[Dict[str, Any]] = None


class JobResponse(BaseModel):
    id: str
    name: Optional[str] = None
    func: str
    next_run_time: str
    trigger: str
    args: List
    kwargs: dict
    status: str


class AvailableTask(BaseModel):
    name: str
    category: str
    description: str
    parameters: Dict[str, Any]


class LogEntry(BaseModel):
    id: int
    job_id: str
    status: str
    message: str
    timestamp: str


class JobLogResponse(BaseModel):
    id: int
    job_id: str
    status: bool
    message: str
    duration: Optional[float] = None
    output: Optional[str] = None
    timestamp: datetime
    
    model_config = {
        "from_attributes": True
    }


class JobLogPage(BaseModel):
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