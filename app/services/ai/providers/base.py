from typing import Any, Dict, List


class AIProviderBase:
    def chat(self, messages: List[Dict[str, Any]], model: str, tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        raise NotImplementedError
