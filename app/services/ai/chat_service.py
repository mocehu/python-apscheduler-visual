import json
import uuid
from typing import Any, Dict, Generator, List

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