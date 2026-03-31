import json
import re
import uuid
from typing import Any, Dict, Generator, List, Optional

from app.core.database import (
    add_ai_message,
    add_ai_tool_call,
    create_ai_session,
    get_ai_session,
    get_config,
    get_config_int,
    list_ai_messages,
)
from app.services.ai.function_registry import call_tool, get_tool_schemas
from app.services.ai.prompts import SYSTEM_PROMPT
from app.services.ai.providers.openai_compatible import OpenAICompatibleProvider


def _message_to_openai(role: str, content: str) -> Dict[str, Any]:
    return {"role": role, "content": content}


def _build_provider(db):
    base_url = get_config(db, "ai_base_url", "https://api.openai.com/v1")
    api_key = get_config(db, "ai_api_key", "")
    return OpenAICompatibleProvider(base_url=base_url, api_key=api_key)


def _prepare_session(db, session_id=None, model=None, mode: str = 'draft'):
    if session_id:
        session = get_ai_session(db, session_id)
        if session:
            return session

    new_session_id = session_id or uuid.uuid4().hex
    model_name = model or get_config(db, "ai_model", "gpt-4o-mini")
    return create_ai_session(db, new_session_id, model=model_name, mode=mode)


def _load_history(db, session_id: str) -> List[Dict[str, Any]]:
    max_history = get_config_int(db, "ai_max_history_messages", 12)
    messages = list_ai_messages(db, session_id, limit=max_history)
    return [_message_to_openai(message.role, message.content) for message in messages]


def chat_once(db, message: str, session_id=None, model=None, mode: str = 'draft') -> Dict[str, Any]:
    session = _prepare_session(db, session_id=session_id, model=model, mode=mode)
    add_ai_message(db, session.id, 'user', message)

    provider = _build_provider(db)
    tools = get_tool_schemas()
    history = _load_history(db, session.id)
    messages = [_message_to_openai('system', SYSTEM_PROMPT)] + history

    all_tool_results = []
    draft = None
    reply_text = ''
    max_iterations = 5
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        response = provider.chat(messages=messages, model=session.model, tools=tools)
        
        if response.get('error'):
            return {
                'session_id': session.id,
                'reply': response.get('message', 'AI API 调用失败'),
                'tool_calls': [{'name': tr['name'], 'arguments': tr['arguments'], 'result': tr['result']} for tr in all_tool_results],
                'draft': draft,
                'model': session.model,
                'provider': session.provider,
                'error': True,
                'error_code': response.get('code'),
            }
        
        choice = response.get('choices', [{}])[0]
        message_data = choice.get('message', {})
        tool_calls = message_data.get('tool_calls', [])
        content = message_data.get('content') or ''
        
        if content:
            reply_text = content
        
        if not tool_calls:
            break
        
        messages.append(message_data)
        
        for tool_call in tool_calls:
            function_data = tool_call.get('function', {})
            tool_name = function_data.get('name')
            arguments = function_data.get('arguments') or '{}'
            parsed_arguments = json.loads(arguments)
            result = call_tool(tool_name, parsed_arguments)
            add_ai_tool_call(db, session.id, tool_name, parsed_arguments, result)
            all_tool_results.append({
                'name': tool_name,
                'arguments': parsed_arguments,
                'result': result,
                'tool_call_id': tool_call.get('id'),
            })
            if result.get('action'):
                draft = result
            
            messages.append({
                'role': 'tool',
                'tool_call_id': tool_call.get('id'),
                'content': json.dumps(result, ensure_ascii=False),
            })

    if not reply_text and all_tool_results:
        messages.append({
            'role': 'user',
            'content': '请根据工具调用结果，用简洁的自然语言回答用户的问题。不要重复介绍自己，直接给出答案。',
        })
        follow_up = provider.chat(messages=messages, model=session.model, tools=tools)
        if follow_up.get('error'):
            reply_text = f"工具执行完成，但生成回复失败: {follow_up.get('message')}"
        else:
            reply_text = follow_up.get('choices', [{}])[0].get('message', {}).get('content') or ''

    assistant_content = reply_text
    add_ai_message(db, session.id, 'assistant', assistant_content)

    return {
        'session_id': session.id,
        'reply': assistant_content,
        'tool_calls': [{'name': tr['name'], 'arguments': tr['arguments'], 'result': tr['result']} for tr in all_tool_results],
        'draft': draft,
        'model': session.model,
        'provider': session.provider,
    }


def chat_stream(db, message: str, session_id=None, model=None, mode: str = 'draft') -> Generator[Dict[str, Any], None, None]:
    session = _prepare_session(db, session_id=session_id, model=model, mode=mode)
    add_ai_message(db, session.id, 'user', message)

    provider = _build_provider(db)
    tools = get_tool_schemas()
    history = _load_history(db, session.id)
    messages = [_message_to_openai('system', SYSTEM_PROMPT)] + history

    yield {"type": "session", "session_id": session.id, "model": session.model}

    full_content = ""
    all_tool_results = []
    draft = None
    max_iterations = 5
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        tool_calls_data = []
        has_error = False
        iteration_content = ""

        for chunk in provider.chat_stream(messages=messages, model=session.model, tools=tools):
            if chunk.get('error'):
                has_error = True
                yield {"type": "error", "message": chunk.get('message', 'AI API 调用失败'), "code": chunk.get('code')}
                continue
            
            delta = chunk.get('choices', [{}])[0].get('delta', {})

            if 'content' in delta and delta['content']:
                content = delta['content']
                iteration_content += content
                full_content += content
                yield {"type": "content", "content": content}

            if 'tool_calls' in delta:
                for tool_call_delta in delta['tool_calls']:
                    idx = tool_call_delta.get('index', 0)
                    while len(tool_calls_data) <= idx:
                        tool_calls_data.append({'id': '', 'type': 'function', 'function': {'name': '', 'arguments': ''}})

                    if 'id' in tool_call_delta:
                        tool_calls_data[idx]['id'] = tool_call_delta['id']
                    if 'function' in tool_call_delta:
                        func = tool_call_delta['function']
                        if 'name' in func:
                            tool_calls_data[idx]['function']['name'] = func['name']
                        if 'arguments' in func:
                            tool_calls_data[idx]['function']['arguments'] += func['arguments']

        if has_error:
            yield {"type": "done", "reply": full_content or "AI API 调用失败"}
            return

        if not tool_calls_data:
            break

        messages.append({
            'role': 'assistant',
            'content': iteration_content or None,
            'tool_calls': [
                {
                    'id': tc['id'],
                    'type': 'function',
                    'function': tc['function'],
                }
                for tc in tool_calls_data
            ],
        })

        for tool_call in tool_calls_data:
            tool_name = tool_call['function']['name']
            arguments = tool_call['function']['arguments'] or '{}'
            try:
                parsed_arguments = json.loads(arguments)
            except json.JSONDecodeError:
                parsed_arguments = {}

            result = call_tool(tool_name, parsed_arguments)
            add_ai_tool_call(db, session.id, tool_name, parsed_arguments, result)
            all_tool_results.append({
                'name': tool_name,
                'arguments': parsed_arguments,
                'result': result,
                'tool_call_id': tool_call['id'],
            })
            if result.get('action'):
                draft = result

            yield {
                "type": "tool_call",
                "name": tool_name,
                "arguments": parsed_arguments,
                "result": result,
            }

            messages.append({
                'role': 'tool',
                'tool_call_id': tool_call['id'],
                'content': json.dumps(result, ensure_ascii=False),
            })

    if not full_content and all_tool_results:
        messages.append({
            'role': 'user',
            'content': '请根据工具调用结果，用简洁的自然语言回答用户的问题。不要重复介绍自己，直接给出答案。',
        })
        yield {"type": "content", "content": "\n"}
        for chunk in provider.chat_stream(messages=messages, model=session.model, tools=tools):
            if chunk.get('error'):
                yield {"type": "error", "message": chunk.get('message')}
                continue
            delta = chunk.get('choices', [{}])[0].get('delta', {})
            if 'content' in delta and delta['content']:
                full_content += delta['content']
                yield {"type": "content", "content": delta['content']}

    assistant_content = full_content
    add_ai_message(db, session.id, 'assistant', assistant_content)

    if draft:
        yield {"type": "draft", "draft": draft}

    yield {"type": "done", "reply": assistant_content}


CODE_GENERATE_PROMPT = """你是专注于 Python 定时任务的工具函数代码生成助手。
请严格按照以下规则，仅生成被定时调用的目标业务函数，禁止实现任何定时调度框架/逻辑，仅保留核心任务函数：

## 强制代码规范
1. 函数结构：仅输出唯一一个主函数，采用 `snake_case` 命名法，无额外类、无依赖、无调度代码；
2. 类型注解：函数必须包含完整标准类型注解，明确标注所有参数类型、返回值类型（支持 `list/dict/Optional/Union` 等标准类型）；
3. 文档字符串：必须编写**标准 Google 风格文档字符串，包含：函数功能、所有参数说明、返回值说明、可能抛出的异常；
4. 日志输出：统一使用 `print()` 输出执行信息（系统会自动捕获）；
5. 返回格式：固定返回字典格式：
   ```python
   {{"output": "执行结果文本", "status": 布尔值, "error": "异常信息（无异常为空字符串）"}}
   ```
6. 依赖要求：优先使用 Python 内置标准库，最好不引入第三方包；
7. 代码纯净：无测试代码、无调用示例、无注释冗余、无多余逻辑，代码可直接嵌入定时任务使用。

## 安全限制

禁止使用以下模块和函数：
- 模块：{forbidden_modules}
- 函数：{forbidden_builtins}

## 输出格式

只输出代码，不要解释。代码格式：

```python
def {func_name}(...):
    ...
```
"""

CODE_REVIEW_PROMPT = """你是一个 Python 代码审查助手。审查用户提供的代码，分析以下方面：

## 审查内容

1. **安全性**：是否使用了禁止的模块或函数
2. **语法**：是否有语法错误
3. **逻辑**：是否有潜在的逻辑问题
4. **规范**：是否符合代码规范

## 安全限制

禁止的模块：{forbidden_modules}
禁止的函数：{forbidden_builtins}

## 输出格式

以 JSON 格式输出审查结果：

```json
{{
  "safe": true/false,
  "errors": ["错误1", "错误2"],
  "warnings": ["警告1", "警告2"],
  "suggestions": ["建议1", "建议2"],
  "summary": "总体评价"
}}
```

只输出 JSON，不要其他内容。
"""


def generate_code(db, description: str, func_name: Optional[str] = None, category: str = "custom") -> Dict[str, Any]:
    """
    根据需求描述生成自定义任务代码
    """
    from app.services.custom_tasks import DEFAULT_FORBIDDEN_MODULES, DEFAULT_FORBIDDEN_BUILTINS
    
    provider = _build_provider(db)
    model = get_config(db, "ai_model", "gpt-4o-mini")
    
    forbidden_modules = ", ".join(DEFAULT_FORBIDDEN_MODULES)
    forbidden_builtins = ", ".join(DEFAULT_FORBIDDEN_BUILTINS)
    
    system_prompt = CODE_GENERATE_PROMPT.format(
        forbidden_modules=forbidden_modules,
        forbidden_builtins=forbidden_builtins,
        func_name=func_name or "custom_task"
    )
    
    user_message = f"需求：{description}"
    if func_name:
        user_message += f"\n函数名：{func_name}"
    if category:
        user_message += f"\n分类：{category}"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]
    
    response = provider.chat(messages=messages, model=model, tools=[])
    
    if response.get('error'):
        return {
            "success": False,
            "error": response.get('message', 'AI API 调用失败'),
            "code": None
        }
    
    content = response.get('choices', [{}])[0].get('message', {}).get('content', '')
    
    code_match = re.search(r'```python\s*(.*?)\s*```', content, re.DOTALL)
    if code_match:
        code = code_match.group(1)
    else:
        code_match = re.search(r'```\s*(.*?)\s*```', content, re.DOTALL)
        code = code_match.group(1) if code_match else content
    
    return {
        "success": True,
        "code": code.strip(),
        "func_name": func_name,
        "category": category,
        "raw_response": content
    }


def generate_code_stream(db, description: str, func_name: Optional[str] = None, category: str = "custom"):
    """
    流式生成代码
    """
    from app.services.custom_tasks import DEFAULT_FORBIDDEN_MODULES, DEFAULT_FORBIDDEN_BUILTINS
    
    provider = _build_provider(db)
    model = get_config(db, "ai_model", "gpt-4o-mini")
    
    forbidden_modules = ", ".join(DEFAULT_FORBIDDEN_MODULES)
    forbidden_builtins = ", ".join(DEFAULT_FORBIDDEN_BUILTINS)
    
    system_prompt = CODE_GENERATE_PROMPT.format(
        forbidden_modules=forbidden_modules,
        forbidden_builtins=forbidden_builtins,
        func_name=func_name or "custom_task"
    )
    
    user_message = f"需求：{description}"
    if func_name:
        user_message += f"\n函数名：{func_name}"
    if category:
        user_message += f"\n分类：{category}"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]
    
    full_content = ""
    
    yield {"type": "status", "message": "正在生成代码..."}
    
    for chunk in provider.chat_stream(messages=messages, model=model, tools=[]):
        if chunk.get("error"):
            yield {"type": "error", "message": chunk.get("message", "AI API 调用失败")}
            return
        
        delta = chunk.get('choices', [{}])[0].get('delta', {})
        if 'content' in delta and delta['content']:
            full_content += delta['content']
            yield {"type": "content", "content": delta['content']}
    
    code_match = re.search(r'```python\s*(.*?)\s*```', full_content, re.DOTALL)
    if code_match:
        code = code_match.group(1)
    else:
        code_match = re.search(r'```\s*(.*?)\s*```', full_content, re.DOTALL)
        code = code_match.group(1) if code_match else full_content
    
    yield {
        "type": "done",
        "code": code.strip(),
        "func_name": func_name,
        "category": category
    }


def review_code(db, code: str, func_name: Optional[str] = None) -> Dict[str, Any]:
    """
    审查代码的安全性和质量
    """
    import json
    from app.services.custom_tasks import DEFAULT_FORBIDDEN_MODULES, DEFAULT_FORBIDDEN_BUILTINS, check_code_security
    
    security_result = check_code_security(code)
    
    provider = _build_provider(db)
    model = get_config(db, "ai_model", "gpt-4o-mini")
    
    forbidden_modules = ", ".join(DEFAULT_FORBIDDEN_MODULES)
    forbidden_builtins = ", ".join(DEFAULT_FORBIDDEN_BUILTINS)
    
    system_prompt = CODE_REVIEW_PROMPT.format(
        forbidden_modules=forbidden_modules,
        forbidden_builtins=forbidden_builtins
    )
    
    user_message = f"请审查以下代码：\n\n```python\n{code}\n```"
    if func_name:
        user_message += f"\n\n函数名：{func_name}"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]
    
    response = provider.chat(messages=messages, model=model, tools=[])
    
    ai_result = {
        "safe": security_result["safe"],
        "errors": security_result["errors"],
        "warnings": security_result["warnings"],
        "suggestions": [],
        "summary": ""
    }
    
    if not response.get('error'):
        content = response.get('choices', [{}])[0].get('message', {}).get('content', '')
        
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            try:
                ai_analysis = json.loads(json_match.group(1))
                ai_result["suggestions"] = ai_analysis.get("suggestions", [])
                ai_result["summary"] = ai_analysis.get("summary", "")
                if ai_analysis.get("errors"):
                    ai_result["errors"].extend(ai_analysis["errors"])
                if ai_analysis.get("warnings"):
                    ai_result["warnings"].extend(ai_analysis["warnings"])
            except json.JSONDecodeError:
                pass
    
    return {
        "success": True,
        "security": ai_result,
        "has_issues": len(ai_result["errors"]) > 0 or len(ai_result["warnings"]) > 0
    }


def review_code_stream(db, code: str, func_name: Optional[str] = None):
    """
    流式审查代码
    """
    import json
    from app.services.custom_tasks import DEFAULT_FORBIDDEN_MODULES, DEFAULT_FORBIDDEN_BUILTINS, check_code_security
    
    security_result = check_code_security(code)
    
    yield {
        "type": "security",
        "safe": security_result["safe"],
        "errors": security_result["errors"],
        "warnings": security_result["warnings"]
    }
    
    if not security_result["safe"]:
        yield {
            "type": "done",
            "security": {
                "safe": False,
                "errors": security_result["errors"],
                "warnings": security_result["warnings"],
                "suggestions": [],
                "summary": "代码存在安全问题，请修复后再使用"
            },
            "has_issues": True
        }
        return
    
    provider = _build_provider(db)
    model = get_config(db, "ai_model", "gpt-4o-mini")
    
    forbidden_modules = ", ".join(DEFAULT_FORBIDDEN_MODULES)
    forbidden_builtins = ", ".join(DEFAULT_FORBIDDEN_BUILTINS)
    
    system_prompt = CODE_REVIEW_PROMPT.format(
        forbidden_modules=forbidden_modules,
        forbidden_builtins=forbidden_builtins
    )
    
    user_message = f"请审查以下代码：\n\n```python\n{code}\n```"
    if func_name:
        user_message += f"\n\n函数名：{func_name}"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]
    
    full_content = ""
    
    yield {"type": "status", "message": "正在分析代码..."}
    
    for chunk in provider.chat_stream(messages=messages, model=model, tools=[]):
        if chunk.get("error"):
            yield {"type": "error", "message": chunk.get("message", "AI API 调用失败")}
            return
        
        delta = chunk.get('choices', [{}])[0].get('delta', {})
        if 'content' in delta and delta['content']:
            full_content += delta['content']
            yield {"type": "content", "content": delta['content']}
    
    ai_result = {
        "safe": security_result["safe"],
        "errors": security_result["errors"],
        "warnings": security_result["warnings"],
        "suggestions": [],
        "summary": ""
    }
    
    json_match = re.search(r'```json\s*(.*?)\s*```', full_content, re.DOTALL)
    if json_match:
        try:
            ai_analysis = json.loads(json_match.group(1))
            ai_result["suggestions"] = ai_analysis.get("suggestions", [])
            ai_result["summary"] = ai_analysis.get("summary", "")
            if ai_analysis.get("errors"):
                ai_result["errors"].extend(ai_analysis["errors"])
            if ai_analysis.get("warnings"):
                ai_result["warnings"].extend(ai_analysis["warnings"])
        except json.JSONDecodeError:
            pass
    
    yield {
        "type": "done",
        "security": ai_result,
        "has_issues": len(ai_result["errors"]) > 0 or len(ai_result["warnings"]) > 0
    }