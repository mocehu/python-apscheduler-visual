import json
import logging
from urllib import error, request

from app.services.ai.providers.base import AIProviderBase

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(AIProviderBase):
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key

    def chat(self, messages, model, tools):
        payload = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.2,
        }
        req = request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as e:
            body = e.read().decode("utf-8") if e.fp else ""
            logger.error(f"AI API HTTP {e.code}: {body}")
            return {
                "error": True,
                "code": e.code,
                "message": f"AI API 错误 ({e.code}): {body[:200]}",
            }
        except error.URLError as e:
            logger.error(f"AI API 网络错误: {e.reason}")
            return {
                "error": True,
                "code": "network",
                "message": f"AI API 网络错误: {e.reason}",
            }

    def chat_stream(self, messages, model, tools):
        payload = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.2,
            "stream": True,
        }
        req = request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=120) as response:
                for line in response:
                    line = line.decode("utf-8").strip()
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            yield json.loads(data)
                        except json.JSONDecodeError:
                            continue
        except error.HTTPError as e:
            body = e.read().decode("utf-8") if e.fp else ""
            logger.error(f"AI API HTTP {e.code}: {body}")
            yield {
                "error": True,
                "code": e.code,
                "message": f"AI API 错误 ({e.code}): {body[:200]}",
            }
        except error.URLError as e:
            logger.error(f"AI API 网络错误: {e.reason}")
            yield {
                "error": True,
                "code": "network",
                "message": f"AI API 网络错误: {e.reason}",
            }