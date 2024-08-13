import json
import os
import socket
import requests

from datebase import get_redis


def is_host_online(host):
    """
    检查主机是否在线。
    """
    response = os.system(f"ping -c 1 {host} > /dev/null 2>&1")
    return response == 0


def is_web_service_online(url):
    """
    检查 Web 服务是否在线。
    """
    try:
        response = requests.get(url, timeout=3)
        print(response.status_code)
        if response.status_code == 200:
            content_bytes = response.content
            content_str = json.loads(content_bytes)
            print(content_str)
            return content_str
        else:
            return None
    except requests.ConnectionError:
        return None


def get_from_redis():
    redis_conn = get_redis()  # 获取Redis连接对象

    # 获取所有与 "status:" 开头匹配的键
    keys = redis_conn.keys("status:*")

    if keys:
        # 使用 mget 批量获取这些键的值
        values = redis_conn.mget(keys)

        # 解析每个 JSON 字符串为字典，并组合为一个字典列表
        statuses = {key.decode('utf-8'): json.loads(value) for key, value in zip(keys, values)}
        print(f"读取自 Redis 的所有状态: {statuses}")
        return statuses
    else:
        print("Redis 中没有找到任何与 'status:' 开头的键")
        return None


def save_to_redis(ip, host_online_status, web_service_status, host_info):
    """
    将检测结果保存到 Redis。
    """
    redis_conn = get_redis()  # 获取Redis连接对象
    redis_key = f"status:{ip}"
    redis_value = {
        "host_online_status": host_online_status,
        "web_service_status": web_service_status,
        "host_info": host_info
    }
    redis_conn.set(redis_key, json.dumps(redis_value), ex=300)
    print(f"保存到 Redis: {redis_key} -> {redis_value}")


def check_host_and_service(host, port=80):
    """
    检查主机和服务状态，区分 Web 服务异常还是主机离线。
    """
    host_online_status = is_host_online(host)
    web_service_status = False
    web_res = None

    if host_online_status:
        print(f"主机 {host} 在线")

        # 检查 Web 服务是否在线
        url = f"http://{host}:{port}/sys/status"
        web_res = is_web_service_online(url)
        if web_res:
            web_service_status = True
            print(f"Web 服务 {url} 正常运行")
        else:
            print(f"Web 服务 {url} 无法访问，可能是服务异常")
    else:
        print(f"主机 {host} 离线")

    save_to_redis(host, host_online_status, web_service_status, web_res)


def start_scan_host():
    """
    外部锚点主机状态扫描
    :return:
    """
    host_map = {
        "47.100.253.200": 8000,
        "124.222.75.44": 8000
    }
    for host, port in host_map.items():
        check_host_and_service(host, port)
