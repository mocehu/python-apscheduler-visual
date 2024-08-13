from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import router
from scheduler import start_scheduler, stop_scheduler
from uvicorn.config import LOGGING_CONFIG


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 此代码将在启动期间运行
    start_scheduler()
    yield
    # 此代码将在关机期间运行
    stop_scheduler()


# 日志格式设置
LOGGING_CONFIG["formatters"]["default"]["fmt"] = "%(asctime)s | %(levelprefix)s| %(funcName)s:%(lineno)d - %(message)s"

app = FastAPI(lifespan=lifespan)

origins = [
    "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
