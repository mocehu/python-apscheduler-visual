import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

VERSION = "1.0.4"
GITHUB_REPO = os.getenv("GITHUB_REPO", "mocehu/fastapi-apscheduler-visual")
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}"

DB_TYPE = os.getenv("DB_TYPE", "sqlite")

if DB_TYPE == "sqlite":
    project_root = Path(__file__).parent.parent.parent
    sqlite_path = project_root / "data" / "scheduler.db"
    DATABASE_URL = f"sqlite:///{sqlite_path.as_posix()}"
else:
    pg_host = os.getenv("POSTGRES_HOST", "localhost")
    pg_port = os.getenv("POSTGRES_PORT", "5432")
    pg_user = os.getenv("POSTGRES_USER", "postgres")
    pg_password = os.getenv("POSTGRES_PASSWORD", "")
    pg_db = os.getenv("POSTGRES_DB", "aps_dev")
    DATABASE_URL = f"postgresql+psycopg2://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

if REDIS_PASSWORD:
    REDIS_URL = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
else:
    REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

API_KEY_ENABLED = os.getenv("API_KEY_ENABLED", "true").lower() == "true"
API_KEY = os.getenv("API_KEY", "123456")

AI_ENABLED = os.getenv("AI_ENABLED", "true").lower() == "true"
AI_PROVIDER = os.getenv("AI_PROVIDER", "openai_compatible")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.openai.com/v1")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini")
AI_ALLOW_EXECUTE = os.getenv("AI_ALLOW_EXECUTE", "false").lower() == "true"
AI_STREAM_ENABLED = os.getenv("AI_STREAM_ENABLED", "true").lower() == "true"
AI_MAX_HISTORY_MESSAGES = int(os.getenv("AI_MAX_HISTORY_MESSAGES", "12"))
AI_AGENT_API_KEY = os.getenv("AI_AGENT_API_KEY", "")
