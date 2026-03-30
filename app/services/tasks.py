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
    return _task_registry.get(task_name)


def get_tasks(category: str = None) -> Dict[str, Callable]:
    if category is not None:
        return _task_categories.get(category, {})
    
    return _task_registry


def get_task_categories() -> List[str]:
    return list(_task_categories.keys())


def get_task_info(task_name: str = None) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    def extract_task_info(name, func):
        sig = func.signature
        params = {}
        
        for param_name, param in sig.parameters.items():
            param_info = {
                "name": param_name,
                "type": str(param.annotation) if param.annotation != inspect.Parameter.empty else "未知",
                "default": str(param.default) if param.default != inspect.Parameter.empty else None,
                "required": param.default == inspect.Parameter.empty
            }
            params[param_name] = param_info
        
        return {
            "name": name,
            "description": func.task_desc,
            "category": func.task_category,
            "parameters": params
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
