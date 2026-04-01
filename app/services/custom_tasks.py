import ast
import logging
import sys
import io
import time
import functools
import inspect
import threading
import traceback
from typing import Dict, List, Any, Optional, Callable, Set
from contextlib import redirect_stdout, redirect_stderr

from sqlalchemy.orm import Session

from app.models.sql_model import CustomTask
from app.services.tasks import _task_registry, _task_categories, OutputCapture

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_FORBIDDEN_MODULES = {
    "pickle", "marshal", "shelve",
    "ctypes",
}

DEFAULT_FORBIDDEN_BUILTINS = {
    "__import__", "compile", "exec", "eval",
    "breakpoint",
}

SAFE_BUILTINS = {
    "abs": abs, "all": all, "any": any, "bin": bin, "bool": bool,
    "chr": chr, "complex": complex, "dict": dict, "divmod": divmod,
    "enumerate": enumerate, "filter": filter, "float": float, "format": format,
    "frozenset": frozenset, "hex": hex, "int": int, "isinstance": isinstance,
    "iter": iter, "len": len, "list": list, "map": map, "max": max,
    "min": min, "next": next, "oct": oct, "ord": ord, "pow": pow,
    "range": range, "repr": repr, "reversed": reversed, "round": round,
    "set": set, "slice": slice, "sorted": sorted, "str": str, "sum": sum,
    "tuple": tuple, "zip": zip, "True": True, "False": False, "None": None,
    "print": print, "type": type, "object": object,
    "getattr": getattr, "setattr": setattr, "delattr": delattr, "hasattr": hasattr,
    "property": property, "super": super, "staticmethod": staticmethod, "classmethod": classmethod,
    "open": open, "input": input,
    "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
    "KeyError": KeyError, "IndexError": IndexError, "RuntimeError": RuntimeError,
    "StopIteration": StopIteration, "ZeroDivisionError": ZeroDivisionError,
    "AttributeError": AttributeError, "NameError": NameError,
    "ArithmeticError": ArithmeticError, "LookupError": LookupError,
    "BaseException": BaseException,
    "bytes": bytes, "bytearray": bytearray, "memoryview": memoryview,
    "exit": exit, "quit": quit, "help": help,
    "globals": globals, "locals": locals, "vars": vars, "dir": dir,
}

DEFAULT_TIMEOUT = 30


def get_security_config(db: Session = None) -> Dict[str, Any]:
    """
    获取安全配置，优先从数据库读取，否则使用默认值
    """
    config = {
        "timeout": DEFAULT_TIMEOUT,
        "forbidden_modules": DEFAULT_FORBIDDEN_MODULES.copy(),
        "forbidden_builtins": DEFAULT_FORBIDDEN_BUILTINS.copy(),
    }
    
    if db is None:
        return config
    
    try:
        from app.core.database import get_config, get_config_int
        
        timeout = get_config_int(db, "custom_task_timeout", DEFAULT_TIMEOUT)
        config["timeout"] = timeout
        
        modules_str = get_config(db, "custom_task_forbidden_modules", "")
        if modules_str:
            config["forbidden_modules"] = set(m.strip() for m in modules_str.split(",") if m.strip())
        
        builtins_str = get_config(db, "custom_task_forbidden_builtins", "")
        if builtins_str:
            config["forbidden_builtins"] = set(b.strip() for b in builtins_str.split(",") if b.strip())
    except Exception as e:
        logger.warning(f"读取安全配置失败，使用默认值: {e}")
    
    return config


class TimeoutException(Exception):
    pass


def _execute_with_timeout(code: str, func_name: str, args: tuple, kwargs: dict, timeout: int) -> Dict[str, Any]:
    """
    在线程中执行代码，带超时限制
    使用 threading 实现，兼容 Windows
    """
    result_container = {"result": None, "error": None, "output": "", "status": False, "completed": False}
    
    def worker():
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        
        sys.stdout = stdout_capture
        sys.stderr = stderr_capture
        
        try:
            safe_globals = {"__builtins__": dict(SAFE_BUILTINS)}
            local_vars = {}
            exec(code, safe_globals, local_vars)
            
            if func_name not in local_vars:
                result_container["error"] = f"函数 {func_name} 未找到"
                result_container["status"] = False
                return
            
            func = local_vars[func_name]
            result = func(*args, **kwargs)
            
            if isinstance(result, dict):
                if result.get("output"):
                    result_container["output"] = result["output"]
                if result.get("error"):
                    result_container["error"] = result["error"]
                if "status" in result:
                    result_container["status"] = result["status"]
                result_container["result"] = result.get("result")
            else:
                result_container["result"] = result
                result_container["status"] = True
            
        except Exception as e:
            result_container["error"] = str(e)
            result_container["status"] = False
            traceback.print_exc()
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            result_container["output"] = stdout_capture.getvalue()
            result_container["completed"] = True
    
    thread = threading.Thread(target=worker)
    thread.daemon = True
    thread.start()
    thread.join(timeout=timeout)
    
    if thread.is_alive():
        return {
            "output": "",
            "result": None,
            "status": False,
            "error": f"执行超时（超过 {timeout} 秒）"
        }
    
    if not result_container["completed"]:
        return {
            "output": "",
            "result": None,
            "status": False,
            "error": "执行异常终止"
        }
    
    return {
        "output": result_container["output"],
        "result": result_container["result"],
        "status": result_container["status"],
        "error": result_container["error"]
    }


def check_code_security(code: str, forbidden_modules: Set[str] = None, 
                        forbidden_builtins: Set[str] = None) -> Dict[str, Any]:
    """
    检查代码安全性，检测危险操作
    
    Args:
        code: 要检查的代码
        forbidden_modules: 禁止导入的模块集合
        forbidden_builtins: 禁止调用的内置函数集合
    
    Returns:
        dict: {"safe": bool, "errors": list, "warnings": list}
    """
    if forbidden_modules is None:
        forbidden_modules = DEFAULT_FORBIDDEN_MODULES
    if forbidden_builtins is None:
        forbidden_builtins = DEFAULT_FORBIDDEN_BUILTINS
    
    errors = []
    warnings = []
    
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return {"safe": False, "errors": [f"语法错误: {e}"], "warnings": []}
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_name = alias.name.split('.')[0]
                if module_name in forbidden_modules:
                    errors.append(f"禁止导入模块: {module_name}")
        
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                module_name = node.module.split('.')[0]
                if module_name in forbidden_modules:
                    errors.append(f"禁止导入模块: {module_name}")
        
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
                if func_name in forbidden_builtins:
                    errors.append(f"禁止调用函数: {func_name}")
        
        elif isinstance(node, ast.Name):
            if node.id in forbidden_builtins and isinstance(node.ctx, ast.Load):
                warnings.append(f"检测到潜在危险标识符: {node.id}")
        
        elif isinstance(node, ast.Attribute):
            if node.attr in ("__import__", "__builtins__", "__globals__", "__code__"):
                errors.append(f"禁止访问内部属性: {node.attr}")
    
    dangerous_patterns = [
        ("__import__", "禁止使用 __import__"),
        ("eval(", "禁止使用 eval"),
        ("exec(", "禁止使用 exec"),
        ("compile(", "禁止使用 compile"),
    ]
    
    for pattern, msg in dangerous_patterns:
        if pattern in code:
            errors.append(msg)
    
    return {
        "safe": len(errors) == 0,
        "errors": errors,
        "warnings": warnings
    }


def create_safe_globals() -> Dict[str, Any]:
    """
    创建安全的执行环境 globals
    """
    safe_globals = {"__builtins__": dict(SAFE_BUILTINS)}
    return safe_globals


def validate_task_code(code: str, name: str, forbidden_modules: Set[str] = None,
                       forbidden_builtins: Set[str] = None) -> Dict[str, Any]:
    """
    验证任务代码是否合法和安全
    
    Args:
        code: 要验证的代码
        name: 函数名
        forbidden_modules: 禁止导入的模块集合
        forbidden_builtins: 禁止调用的内置函数集合
    
    Returns:
        dict: {"valid": bool, "error": str or None, "params": dict or None, "warnings": list or None}
    """
    security_check = check_code_security(code, forbidden_modules, forbidden_builtins)
    if not security_check["safe"]:
        return {
            "valid": False,
            "error": "代码安全检查失败: " + "; ".join(security_check["errors"]),
            "params": None,
            "warnings": security_check["warnings"]
        }
    
    try:
        safe_globals = create_safe_globals()
        local_vars = {}
        exec(code, safe_globals, local_vars)
        
        if name not in local_vars:
            return {"valid": False, "error": f"代码中未找到函数 '{name}'", "params": None, "warnings": None}
        
        func = local_vars[name]
        if not callable(func):
            return {"valid": False, "error": f"'{name}' 不是可调用函数", "params": None, "warnings": None}
        
        sig = inspect.signature(func)
        params = {}
        for param_name, param in sig.parameters.items():
            params[param_name] = {
                "name": param_name,
                "type": str(param.annotation) if param.annotation != inspect.Parameter.empty else "any",
                "default": str(param.default) if param.default != inspect.Parameter.empty else None,
                "required": param.default == inspect.Parameter.empty
            }
        
        return {
            "valid": True,
            "error": None,
            "params": params,
            "warnings": security_check["warnings"]
        }
    except SyntaxError as e:
        return {"valid": False, "error": f"语法错误: {e}", "params": None, "warnings": None}
    except NameError as e:
        return {"valid": False, "error": f"未定义的变量或函数: {e}", "params": None, "warnings": None}
    except Exception as e:
        return {"valid": False, "error": str(e), "params": None, "warnings": None}


def create_task_wrapper(code: str, task_name: str, task_desc: str, task_category: str, 
                         use_timeout: bool = True, timeout: int = None) -> Callable:
    """
    为自定义任务函数创建安全包装器
    """
    if timeout is None:
        timeout = DEFAULT_TIMEOUT
    
    safe_globals = create_safe_globals()
    local_vars = {}
    exec(code, safe_globals, local_vars)
    func = local_vars[task_name]
    sig = inspect.signature(func)
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        
        if use_timeout:
            result = _execute_with_timeout(code, task_name, args, kwargs, timeout)
        else:
            with OutputCapture() as capture:
                try:
                    result = func(*args, **kwargs)
                    status = True
                    error = None
                except Exception as e:
                    result = None
                    status = False
                    error = str(e)
                    logger.error(f"任务 {task_name} 执行出错: {e}")
            
            output = capture.get_output()
            
            if isinstance(result, dict):
                if result.get("output"):
                    output = result["output"]
                if result.get("error"):
                    error = result["error"]
                if "status" in result:
                    status = result["status"]
                result = result.get("result")
            
            result = {
                "output": output,
                "result": result,
                "status": status,
                "error": error
            }
        
        end_time = time.time()
        elapsed_time = (end_time - start_time) * 1000
        
        result["elapsed_time"] = elapsed_time
        return result
    
    wrapper.original_func = func
    wrapper.task_name = task_name
    wrapper.task_desc = task_desc
    wrapper.task_category = task_category
    wrapper.signature = sig
    wrapper.use_timeout = use_timeout
    wrapper.timeout = timeout
    wrapper.code = code
    
    return wrapper


def register_custom_task(task_name: str, task_desc: str, task_category: str, code: str,
                         use_timeout: bool = True, timeout: int = None) -> bool:
    """
    注册自定义任务到任务注册表（安全模式）
    """
    if timeout is None:
        timeout = DEFAULT_TIMEOUT
    
    try:
        wrapper = create_task_wrapper(code, task_name, task_desc, task_category, use_timeout, timeout)
        
        if task_category not in _task_categories:
            _task_categories[task_category] = {}
        
        _task_registry[task_name] = wrapper
        _task_categories[task_category][task_name] = wrapper
        
        logger.info(f"注册自定义任务: {task_name} [分类: {task_category}] [安全模式: 超时保护]")
        return True
    except Exception as e:
        logger.error(f"注册自定义任务 {task_name} 失败: {e}")
        return False


def unregister_custom_task(task_name: str) -> bool:
    """
    从任务注册表移除自定义任务
    """
    if task_name not in _task_registry:
        return False
    
    wrapper = _task_registry[task_name]
    category = wrapper.task_category
    
    del _task_registry[task_name]
    
    if category in _task_categories and task_name in _task_categories[category]:
        del _task_categories[category][task_name]
    
    logger.info(f"移除自定义任务: {task_name}")
    return True


def get_custom_task(db: Session, name: str) -> Optional[CustomTask]:
    return db.query(CustomTask).filter(CustomTask.name == name).first()


def get_custom_tasks(db: Session, enabled_only: bool = False) -> List[CustomTask]:
    query = db.query(CustomTask)
    if enabled_only:
        query = query.filter(CustomTask.enabled == True)
    return query.all()


def is_task_used(func_name: str) -> Dict[str, Any]:
    """
    检查任务函数是否被计划任务使用
    
    Returns:
        dict: {"used": bool, "jobs": [job_id1, job_id2, ...]}
    """
    from app.services.scheduler import get_all_jobs
    
    jobs = get_all_jobs()
    used_by = []
    
    for job in jobs:
        if job.get("func") == func_name:
            used_by.append(job.get("id"))
    
    return {"used": len(used_by) > 0, "jobs": used_by}


def get_task_parameters(code: str, func_name: str) -> Dict[str, Any]:
    """
    解析任务函数的参数信息，包括从 docstring 提取参数描述
    
    支持 Google、NumPy、Sphinx/reST 格式的 docstring
    """
    from app.services.docstring_parser import parse_docstring
    
    try:
        safe_globals = create_safe_globals()
        local_vars = {}
        exec(code, safe_globals, local_vars)
        
        if func_name not in local_vars:
            return {}
        
        func = local_vars[func_name]
        sig = inspect.signature(func)
        
        docstring = func.__doc__
        func_desc, doc_params = parse_docstring(docstring) if docstring else ("", {})
        
        params = {}
        for param_name, param in sig.parameters.items():
            param_info = {
                "name": param_name,
                "type": str(param.annotation) if param.annotation != inspect.Parameter.empty else "any",
                "default": str(param.default) if param.default != inspect.Parameter.empty else None,
                "required": param.default == inspect.Parameter.empty,
                "description": doc_params.get(param_name, {}).get("description", "")
            }
            
            if doc_params.get(param_name, {}).get("type"):
                param_info["docstring_type"] = doc_params[param_name]["type"]
            
            params[param_name] = param_info
        
        return params
    except Exception as e:
        logger.error(f"解析任务参数失败: {e}")
        return {}


def create_custom_task(db: Session, name: str, category: str, description: str, code: str) -> CustomTask:
    existing = get_custom_task(db, name)
    if existing:
        raise ValueError(f"任务名称 '{name}' 已存在")
    
    validation = validate_task_code(code, name)
    if not validation["valid"]:
        raise ValueError(validation["error"])
    
    if validation["warnings"]:
        logger.warning(f"任务 {name} 安全警告: {validation['warnings']}")
    
    custom_task = CustomTask(
        name=name,
        category=category,
        description=description,
        code=code,
        enabled=True
    )
    db.add(custom_task)
    db.commit()
    db.refresh(custom_task)
    
    register_custom_task(name, description or "自定义任务", category, code)
    
    logger.info(f"创建自定义任务: {name}")
    return custom_task


def update_custom_task(db: Session, name: str, category: Optional[str] = None, 
                       description: Optional[str] = None, code: Optional[str] = None,
                       enabled: Optional[bool] = None, force: bool = False) -> CustomTask:
    custom_task = get_custom_task(db, name)
    if not custom_task:
        raise ValueError(f"任务 '{name}' 不存在")
    
    usage = is_task_used(name)
    if usage["used"] and not force:
        raise ValueError(f"任务 '{name}' 正在被以下计划任务使用: {', '.join(usage['jobs'])}，无法修改。如需强制修改请使用 force=true")
    
    if code is not None:
        validation = validate_task_code(code, name)
        if not validation["valid"]:
            raise ValueError(validation["error"])
        if validation["warnings"]:
            logger.warning(f"任务 {name} 安全警告: {validation['warnings']}")
        custom_task.code = code
    
    if category is not None:
        custom_task.category = category
    if description is not None:
        custom_task.description = description
    if enabled is not None:
        custom_task.enabled = enabled
    
    db.commit()
    db.refresh(custom_task)
    
    if custom_task.enabled:
        unregister_custom_task(name)
        register_custom_task(name, custom_task.description or "自定义任务", 
                            custom_task.category, custom_task.code)
    else:
        unregister_custom_task(name)
    
    logger.info(f"更新自定义任务: {name}")
    return custom_task


def delete_custom_task(db: Session, name: str, force: bool = False) -> bool:
    custom_task = get_custom_task(db, name)
    if not custom_task:
        return False
    
    usage = is_task_used(name)
    if usage["used"] and not force:
        raise ValueError(f"任务 '{name}' 正在被以下计划任务使用: {', '.join(usage['jobs'])}，无法删除。请先删除相关计划任务")
    
    unregister_custom_task(name)
    db.delete(custom_task)
    db.commit()
    
    logger.info(f"删除自定义任务: {name}")
    return True


def load_custom_tasks(db: Session) -> Dict[str, Any]:
    """
    加载所有已启用的自定义任务
    """
    custom_tasks = get_custom_tasks(db, enabled_only=True)
    
    loaded = []
    errors = []
    
    for task in custom_tasks:
        try:
            success = register_custom_task(
                task.name, 
                task.description or "自定义任务",
                task.category,
                task.code
            )
            if success:
                loaded.append(task.name)
            else:
                errors.append(f"{task.name}: 注册失败")
        except Exception as e:
            errors.append(f"{task.name}: {str(e)}")
    
    result = {
        "loaded": loaded,
        "errors": errors if errors else None,
        "total": len(custom_tasks)
    }
    
    logger.info(f"加载自定义任务完成: {len(loaded)}/{len(custom_tasks)}")
    return result


def execute_custom_task_code(func_name: str, args: tuple, kwargs: dict) -> Dict[str, Any]:
    """
    执行自定义任务代码（由调度器调用）
    
    Args:
        func_name: 任务函数名
        args: 位置参数
        kwargs: 关键字参数
    
    Returns:
        执行结果
    """
    from app.core.database import _session_factory
    
    # 先从注册表查找
    if func_name in _task_registry:
        wrapper = _task_registry[func_name]
        return wrapper(*args, **kwargs)
    
    # 注册表没有，从数据库加载
    db = _session_factory()
    try:
        custom_task = db.query(CustomTask).filter(
            CustomTask.name == func_name,
            CustomTask.enabled == True
        ).first()
        
        if not custom_task:
            raise ValueError(f"自定义任务 '{func_name}' 不存在或已禁用")
        
        # 临时注册并执行
        register_custom_task(
            func_name,
            custom_task.description or "自定义任务",
            custom_task.category,
            custom_task.code
        )
        
        wrapper = _task_registry[func_name]
        return wrapper(*args, **kwargs)
    finally:
        db.close()


def load_custom_task_from_db(func_name: str) -> Optional[Callable]:
    """
    从数据库加载自定义任务到注册表
    
    Args:
        func_name: 任务函数名
    
    Returns:
        任务包装器，如果不存在返回 None
    """
    from app.core.database import _session_factory
    
    db = _session_factory()
    try:
        custom_task = db.query(CustomTask).filter(
            CustomTask.name == func_name,
            CustomTask.enabled == True
        ).first()
        
        if not custom_task:
            return None
        
        # 注册到注册表
        success = register_custom_task(
            func_name,
            custom_task.description or "自定义任务",
            custom_task.category,
            custom_task.code
        )
        
        if success:
            return _task_registry.get(func_name)
        return None
    except Exception as e:
        logger.error(f"从数据库加载自定义任务 {func_name} 失败: {e}")
        return None
    finally:
        db.close()