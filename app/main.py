from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.services.scheduler import start_scheduler, stop_scheduler
from app.core.database import init_db
from uvicorn.config import LOGGING_CONFIG
from app.core.conf import HOST, PORT


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield
    stop_scheduler()


LOGGING_CONFIG["formatters"]["default"]["fmt"] = "%(asctime)s | %(levelprefix)s| %(funcName)s:%(lineno)d - %(message)s"

app = FastAPI(lifespan=lifespan)

origins = ["*"]

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
    uvicorn.run(app, host=HOST, port=PORT)