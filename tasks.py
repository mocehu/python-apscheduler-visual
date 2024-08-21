import functools
import inspect
import io
import os
import sys
import time
from contextlib import redirect_stdout


def example_task(arg1: str, arg2: int = 10):
    """
    示例任务
    :param arg1:
    :param arg2:
    :return:
    """

    # 创建一个字符串缓冲区
    start_time = time.time()
    f = io.StringIO()

    # 将输出重定向到缓冲区
    with redirect_stdout(f):
        print(f"执行任务，参数: {arg1}, {arg2}")

    # 获取所有输出内容
    output = f.getvalue()
    end_time = time.time()
    elapsed_time = (end_time - start_time) * 1000
    return elapsed_time, output


def run_os_command(command: str):
    """
    在操作系统终端执行命令
    :param command:
    :return:
    """
    start_time = time.time()
    f = io.StringIO()

    # 将输出重定向到缓冲区
    with redirect_stdout(f):
        os.system(command)
        print(f"执行命令:{command}")

    # 获取所有输出内容
    output = f.getvalue()
    end_time = time.time()
    elapsed_time = (end_time - start_time) * 1000
    return elapsed_time, output


def run_python_command(command: str):
    """
    运行Python代码并返回输出和错误信息
    :param command: 要执行的Python代码
    :return: (output, error) 元组，其中output是命令的标准输出，error是标准错误
    """
    # 创建一个字符串缓冲区
    start_time = time.time()
    f = io.StringIO()

    # 将输出重定向到缓冲区
    with redirect_stdout(f):
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

        print("Output:", output)
        print("Error:", error)

    # 获取所有输出内容
    output = f.getvalue()
    end_time = time.time()
    elapsed_time = (end_time - start_time) * 1000
    return elapsed_time, output


def task_tmp_func():
    """
    任务函数模板
    :return: 执行耗时，输出内容
    """
    # 创建一个字符串缓冲区
    start_time = time.time()
    f = io.StringIO()

    # 将输出重定向到缓冲区
    with redirect_stdout(f):
        pass

    # 获取所有输出内容
    output = f.getvalue()
    end_time = time.time()
    elapsed_time = (end_time - start_time) * 1000
    return elapsed_time, output


def get_tasks():
    """
    自动发现此模块中的所有任务函数。
    """
    func_whitelist = ['get_tasks', 'capture_print', 'task_tmp_func']
    task_functions = {}
    for name, obj in globals().items():
        if name in func_whitelist:
            continue
        if inspect.isfunction(obj) and obj.__module__ == __name__:
            task_functions[name] = obj
    return task_functions
