"""
任务系统模块，提供任务注册、发现和执行功能。
"""

import functools
import inspect
import io
import os
import sys
import time
import importlib
import pkgutil
import logging
import threading
from typing import Dict, List, Any, Callable, Tuple, Optional, Union
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_task_registry = {}
_task_categories = {}


class OutputCapture:
    """捕获所有输出，包括 stdout、stderr 和 subprocess 输出"""
    
    def __init__(self):
        self.stdout_capture = io.StringIO()
        self.stderr_capture = io.StringIO()
        self._original_stdout = None
        self._original_stderr = None
        self._original_stdout_fd = None
        self._original_stderr_fd = None
        self._capture_file = None
    
    def __enter__(self):
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        sys.stdout = self.stdout_capture
        sys.stderr = self.stderr_capture
        
        if hasattr(sys.stdout, 'fileno') and hasattr(os, 'dup'):
            try:
                self._original_stdout_fd = os.dup(1)
                self._original_stderr_fd = os.dup(2)
                self._capture_file = io.StringIO()
                capture_fd = self._capture_file.fileno() if hasattr(self._capture_file, 'fileno') else None
            except (OSError, AttributeError):
                pass
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout = self._original_stdout
        sys.stderr = self._original_stderr
        
        if self._original_stdout_fd is not None:
            try:
                os.dup2(self._original_stdout_fd, 1)
                os.close(self._original_stdout_fd)
            except OSError:
                pass
        
        if self._original_stderr_fd is not None:
            try:
                os.dup2(self._original_stderr_fd, 2)
                os.close(self._original_stderr_fd)
            except OSError:
                pass
        
        return False
    
    def get_output(self) -> str:
        return self.stdout_capture.getvalue()
    
    def get_error(self) -> str:
        return self.stderr_capture.getvalue()


def task(category: str = "default", name: str = None, description: str = None):
    def decorator(func):
        task_name = name or func.__name__
        task_desc = description or func.__doc__ or "无描述"
        
        sig = inspect.signature(func)
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            
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
            
            end_time = time.time()
            elapsed_time = (end_time - start_time) * 1000
            
            return {
                "elapsed_time": elapsed_time,
                "output": output,
                "result": result,
                "status": status,
                "error": error
            }
        
        wrapper.original_func = func
        wrapper.task_name = task_name
        wrapper.task_desc = task_desc
        wrapper.task_category = category
        wrapper.signature = sig
        
        if category not in _task_categories:
            _task_categories[category] = {}
        
        _task_registry[task_name] = wrapper
        _task_categories[category][task_name] = wrapper
        
        logger.info(f"注册任务: {task_name} [分类: {category}]")
        return wrapper
    
    return decorator


@task(category="system", description="在操作系统终端执行命令")
def run_os_command(command: str):
    import subprocess
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300
        )
        output = result.stdout
        error = result.stderr
        if result.returncode != 0 and error:
            return {"output": output, "error": error, "status": False}
        return {"output": output, "error": error, "status": True}
    except subprocess.TimeoutExpired:
        return {"output": "", "error": "命令执行超时", "status": False}
    except Exception as e:
        return {"output": "", "error": str(e), "status": False}


@task(category="system", description="执行Python代码并返回结果")
def run_python_command(command: str):
    old_stdout = sys.stdout
    old_stderr = sys.stderr

    new_stdout = io.StringIO()
    new_stderr = io.StringIO()

    sys.stdout = new_stdout
    sys.stderr = new_stderr

    output = ''
    error = ''

    try:
        exec(command, globals())
        output = new_stdout.getvalue()
        error = new_stderr.getvalue()
    except Exception as e:
        error = str(e)

    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    return {"output": output, "error": error}


@task(category="system", description="自动清理过期日志")
def auto_cleanup_logs():
    from app.core.database import _session_factory, cleanup_old_logs
    db = _session_factory()
    try:
        result = cleanup_old_logs(db)
        print(f"日志清理完成: 按时间删除 {result['deleted_by_age']} 条, 按数量删除 {result['deleted_by_count']} 条")
        return result
    finally:
        db.close()


@task(category="system", description="获取日志统计信息")
def get_logs_statistics():
    from app.core.database import _session_factory, get_log_stats
    db = _session_factory()
    try:
        stats = get_log_stats(db)
        print(f"日志总数: {stats['total_count']}")
        print(f"成功日志: {stats['success_count']}")
        print(f"失败日志: {stats['fail_count']}")
        print(f"过期日志: {stats['expired_count']}")
        return stats
    finally:
        db.close()


@task(category="example", description="示例任务，展示参数传递")
def example_task(arg1: str, arg2: int = 10):
    print(f"执行任务，参数: {arg1}, {arg2}")
    return f"任务执行成功，参数: {arg1}, {arg2}"


def discover_task_modules(package_name: str = None, directory: str = None):
    modules_loaded = []
    
    if package_name:
        try:
            package = importlib.import_module(package_name)
            package_path = getattr(package, "__path__", [])
            
            for _, name, is_pkg in pkgutil.iter_modules(package_path):
                full_name = f"{package_name}.{name}"
                try:
                    importlib.import_module(full_name)
                    modules_loaded.append(full_name)
                    logger.info(f"从包 {package_name} 加载任务模块: {name}")
                except ImportError as e:
                    logger.error(f"无法导入模块 {full_name}: {e}")
        except ImportError as e:
            logger.error(f"无法导入包 {package_name}: {e}")
    
    if directory:
        try:
            dir_path = Path(directory)
            if dir_path.exists() and dir_path.is_dir():
                for file in dir_path.glob("*.py"):
                    if file.name.startswith("_"):
                        continue
                    
                    module_name = file.stem
                    module_path = str(file.absolute())
                    
                    try:
                        spec = importlib.util.spec_from_file_location(module_name, module_path)
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        modules_loaded.append(module_name)
                        logger.info(f"从目录 {directory} 加载任务模块: {module_name}")
                    except Exception as e:
                        logger.error(f"无法加载模块 {module_path}: {e}")
            else:
                logger.error(f"目录不存在或不是一个目录: {directory}")
        except Exception as e:
            logger.error(f"扫描目录 {directory} 时出错: {e}")
    
    return modules_loaded


def get_task(task_name: str) -> Optional[Callable]:
    if task_name in _task_registry:
        return _task_registry[task_name]
    
    # 尝试从数据库加载自定义任务
    from app.services.custom_tasks import load_custom_task_from_db
    return load_custom_task_from_db(task_name)


def get_tasks(category: str = None) -> Dict[str, Callable]:
    if category is not None:
        return _task_categories.get(category, {})
    
    return _task_registry


def get_task_categories() -> List[str]:
    return list(_task_categories.keys())


def get_task_info(task_name: str = None) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    from app.services.docstring_parser import parse_docstring
    
    def extract_task_info(name, func):
        sig = func.signature
        params = {}
        
        original_func = getattr(func, 'original_func', None)
        docstring = original_func.__doc__ if original_func else None
        func_desc, doc_params = parse_docstring(docstring) if docstring else ("", {})
        
        for param_name, param in sig.parameters.items():
            param_info = {
                "name": param_name,
                "type": str(param.annotation) if param.annotation != inspect.Parameter.empty else "未知",
                "default": str(param.default) if param.default != inspect.Parameter.empty else None,
                "required": param.default == inspect.Parameter.empty,
                "description": doc_params.get(param_name, {}).get("description", "")
            }
            
            if doc_params.get(param_name, {}).get("type"):
                param_info["docstring_type"] = doc_params[param_name]["type"]
            
            params[param_name] = param_info
        
        is_custom = hasattr(func, 'code')
        
        return {
            "name": name,
            "description": func.task_desc,
            "category": func.task_category,
            "parameters": params,
            "is_custom": is_custom
        }
    
    if task_name:
        task = get_task(task_name)
        if not task:
            return None
        return extract_task_info(task_name, task)
    
    return [extract_task_info(name, func) for name, func in _task_registry.items()]


def initialize_tasks(packages=None, directories=None):
    if packages:
        for package in packages:
            discover_task_modules(package_name=package)
    
    if directories:
        for directory in directories:
            discover_task_modules(directory=directory)
    
    logger.info(f"任务系统初始化完成，共加载 {len(_task_registry)} 个任务")
    return _task_registry


def reload_tasks(packages=None, directories=None, clear_existing=False):
    """
    重新加载任务模块
    
    Args:
        packages: 要加载的包名列表
        directories: 要扫描的目录列表
        clear_existing: 是否清除现有任务注册表
    
    Returns:
        dict: 包含加载结果的信息
    """
    if clear_existing:
        cleared_count = len(_task_registry)
        _task_registry.clear()
        _task_categories.clear()
        logger.info(f"已清除 {cleared_count} 个已注册任务")
    
    before_count = len(_task_registry)
    loaded_modules = []
    errors = []
    
    if packages:
        for package in packages:
            try:
                modules = discover_task_modules(package_name=package)
                loaded_modules.extend(modules)
            except Exception as e:
                errors.append(f"包 {package}: {str(e)}")
                logger.error(f"加载包 {package} 失败: {e}")
    
    if directories:
        for directory in directories:
            try:
                modules = discover_task_modules(directory=directory)
                loaded_modules.extend(modules)
            except Exception as e:
                errors.append(f"目录 {directory}: {str(e)}")
                logger.error(f"加载目录 {directory} 失败: {e}")
    
    after_count = len(_task_registry)
    new_count = after_count - before_count
    
    result = {
        "total_tasks": after_count,
        "new_tasks": new_count,
        "loaded_modules": loaded_modules,
        "errors": errors if errors else None
    }
    
    logger.info(f"任务重载完成，共 {after_count} 个任务，新增 {new_count} 个")
    return result


def custom_task_dispatcher(func_name: str, *args, **kwargs):
    """
    自定义任务调度器，用于 APScheduler 序列化
    
    这个函数作为所有自定义任务的入口点，APScheduler 可以正确序列化它。
    执行时从注册表或数据库加载实际的代码并执行。
    """
    from app.services.custom_tasks import execute_custom_task_code
    
    return execute_custom_task_code(func_name, args, kwargs)
