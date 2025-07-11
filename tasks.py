"""
任务系统模块，提供任务注册、发现和执行功能。

如何使用:
1. 使用@task装饰器注册任务函数
   ```python
   @task(category="my_category", description="我的任务描述")
   def my_task_function(param1, param2=10):
       # 任务实现
       return result
   ```

2. 创建任务模块示例:
   创建一个名为custom_tasks.py的文件:
   ```python
   from tasks import task
   
   @task(category="custom", description="自定义任务")
   def custom_task(name: str, times: int = 1):
       '''这是一个自定义任务的示例'''
       result = []
       for i in range(times):
           result.append(f"Hello {name}, iteration {i+1}")
       return "\\n".join(result)
   ```

3. 初始化任务系统:
   ```python
   from tasks import initialize_tasks
   
   # 加载当前模块和指定目录中的任务
   initialize_tasks(directories=["./custom_tasks_dir"])
   ```
"""

import functools
import importlib
import inspect
import io
import logging
import pkgutil
import subprocess
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path
from typing import Dict, List, Any, Callable, Optional, Union

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 全局任务注册表
_task_registry = {}
_task_categories = {}

def task(category: str = "default", name: str = None, description: str = None):
    """
    任务装饰器，用于注册任务函数
    
    :param category: 任务分类
    :param name: 任务名称，默认使用函数名
    :param description: 任务描述，默认使用函数文档
    :return: 装饰器
    """
    def decorator(func):
        task_name = name or func.__name__
        task_desc = description or func.__doc__ or "无描述"
        
        # 捕获原始函数签名
        sig = inspect.signature(func)
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 创建一个字符串缓冲区
            start_time = time.time()
            f = io.StringIO()
            
            # 将输出重定向到缓冲区
            with redirect_stdout(f):
                try:
                    result = func(*args, **kwargs)
                    status = True
                    error = None
                except Exception as e:
                    result = None
                    status = False
                    error = str(e)
                    logger.error(f"任务 {task_name} 执行出错: {e}")
            
            # 获取所有输出内容
            output = f.getvalue()
            end_time = time.time()
            elapsed_time = (end_time - start_time) * 1000
            
            # 统一返回格式
            return {
                "elapsed_time": elapsed_time,
                "output": output,
                "result": result,
                "status": status,
                "error": error
            }
        
        # 保存原始函数的元数据
        wrapper.original_func = func
        wrapper.task_name = task_name
        wrapper.task_desc = task_desc
        wrapper.task_category = category
        wrapper.signature = sig
        
        # 注册任务
        if category not in _task_categories:
            _task_categories[category] = {}
        
        _task_registry[task_name] = wrapper
        _task_categories[category][task_name] = wrapper
        
        logger.info(f"注册任务: {task_name} [分类: {category}]")
        return wrapper
    
    return decorator


@task(category="system", description="在操作系统终端执行命令")
def run_os_command(command: str):
    """
    在操作系统终端执行命令
    :param command: 要执行的命令
    :return: 命令输出
    """
    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"命令执行失败: {result.stderr.strip()}")
    print(result.stdout.strip())
    return f"执行命令: {command} 完成"


@task(category="system", description="执行Python代码并返回结果")
def run_python_command(command: str):
    """
    运行Python代码并返回输出和错误信息
    :param command: 要执行的Python代码
    :return: 命令输出
    """
    # 保存当前的stdout和stderr
    old_stdout = sys.stdout
    old_stderr = sys.stderr

    # 使用StringIO来捕获输出
    new_stdout = io.StringIO()
    new_stderr = io.StringIO()

    sys.stdout = new_stdout
    sys.stderr = new_stderr

    output = ''
    error = ''

    try:
        # 执行Python代码
        exec(command, globals())
        output = new_stdout.getvalue()
        error = new_stderr.getvalue()
    except Exception as e:
        # 捕获异常并记录到error中
        error = str(e)

    finally:
        # 恢复原来的stdout和stderr
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    return {"output": output, "error": error}


@task(category="example", description="示例任务，展示参数传递")
def example_task(arg1: str, arg2: int = 10):
    """
    示例任务，用于测试任务系统
    :param arg1: 第一个参数
    :param arg2: 第二个参数，默认为10
    :return: 执行结果
    """
    print(f"执行任务，参数: {arg1}, {arg2}")
    return f"任务执行成功，参数: {arg1}, {arg2}"


def discover_task_modules(package_name: str = None, directory: str = None):
    """
    从包或目录中发现并导入任务模块
    
    :param package_name: 包名
    :param directory: 目录路径
    """
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
    """
    获取指定名称的任务
    
    :param task_name: 任务名称
    :return: 任务函数或None
    """
    return _task_registry.get(task_name)


def get_tasks(category: str = None) -> Dict[str, Callable]:
    """
    获取所有注册的任务或指定分类的任务
    
    :param category: 任务分类，如果为None则返回所有任务
    :return: 任务字典 {名称: 函数}
    """
    if category is not None:
        return _task_categories.get(category, {})
    
    return _task_registry


def get_task_categories() -> List[str]:
    """
    获取所有任务分类
    
    :return: 分类列表
    """
    return list(_task_categories.keys())


def get_task_info(task_name: str = None) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    获取任务详细信息
    
    :param task_name: 任务名称，如果为None则返回所有任务信息
    :return: 任务信息字典或列表
    """
    def extract_task_info(name, func):
        sig = func.signature
        params = {}
        
        for param_name, param in sig.parameters.items():
            param_info = {
                "name": param_name,
                "type": str(param.annotation.__name__) if param.annotation != inspect.Parameter.empty else "未知",
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
    """
    初始化任务系统，加载所有任务模块
    
    :param packages: 要加载的包列表
    :param directories: 要扫描的目录列表
    """
    if packages:
        for package in packages:
            discover_task_modules(package_name=package)
    
    if directories:
        for directory in directories:
            discover_task_modules(directory=directory)
    
    logger.info(f"任务系统初始化完成，共加载 {len(_task_registry)} 个任务")
    return _task_registry
