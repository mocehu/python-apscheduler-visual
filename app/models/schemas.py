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
    id: Optional[str] = None
    job_id: Optional[str] = None
    name: Optional[str] = None
    trigger_args: Optional[Dict[str, Any]] = None
    
    def get_job_id(self) -> Optional[str]:
        return self.id or self.job_id


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
    is_custom: bool = False


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


class AIChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    model: Optional[str] = None
    mode: str = 'draft'


class AIConfigUpdateRequest(BaseModel):
    ai_enabled: Optional[str] = None
    ai_provider: Optional[str] = None
    ai_base_url: Optional[str] = None
    ai_api_key: Optional[str] = None
    ai_model: Optional[str] = None
    ai_allow_execute: Optional[str] = None
    ai_stream_enabled: Optional[str] = None
    ai_agent_api_key: Optional[str] = None
    ai_max_history_messages: Optional[str] = None


class CodeGenerateRequest(BaseModel):
    description: str
    func_name: Optional[str] = None
    category: Optional[str] = "custom"


class CodeReviewRequest(BaseModel):
    code: str
    func_name: Optional[str] = None


class AISessionResponse(BaseModel):
    id: str
    title: Optional[str] = None
    provider: str
    model: str
    mode: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AIMessageResponse(BaseModel):
    id: int
    session_id: str
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AIToolCallResponse(BaseModel):
    id: int
    session_id: str
    message_id: Optional[int] = None
    tool_name: str
    tool_args: Optional[str] = None
    tool_result: Optional[str] = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AISessionDetailResponse(BaseModel):
    session: AISessionResponse
    messages: List[AIMessageResponse]
    tool_calls: List[AIToolCallResponse]


class AIChatResponse(BaseModel):
    session_id: str
    reply: str
    tool_calls: List[Dict[str, Any]]
    draft: Optional[Dict[str, Any]] = None
    model: str
    provider: str


TYPE_MAP = {
    str: 'string',
    int: 'int',
    float: 'float',
    bool: 'bool',
    list: 'list',
    dict: 'dict',
    None: 'any'
}


class CustomTaskCreate(BaseModel):
    name: str
    category: str = 'custom'
    description: Optional[str] = None
    code: str


class CustomTaskUpdate(BaseModel):
    category: Optional[str] = None
    description: Optional[str] = None
    code: Optional[str] = None
    enabled: Optional[bool] = None


class CustomTaskResponse(BaseModel):
    name: str
    category: str
    description: Optional[str] = None
    code: str
    enabled: bool
    created_at: datetime
    updated_at: datetime
    parameters: Optional[Dict[str, Any]] = None
    is_used: bool = False
    used_by_jobs: List[str] = []

    model_config = {"from_attributes": True}
