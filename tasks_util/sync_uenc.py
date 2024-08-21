import base64
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List

import requests

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from datebase import get_db
from sql_model import UencVoiaem


def encrypt(plain_text, key):
    # 将字符串转换为字节数组
    byte_array = bytearray(plain_text, 'utf-8')
    key_byte = ord(key)  # 使用单个字符作为密钥

    # 对每个字节进行按位异或操作
    encrypted_bytes = bytearray([b ^ key_byte for b in byte_array])

    # 将加密后的字节数组转换为Base64编码的字符串
    encrypted_text = base64.b64encode(encrypted_bytes).decode('utf-8')
    return encrypted_text


def decrypt(encrypted_text, key):
    # 将Base64编码的字符串解码为字节数组
    encrypted_bytes = bytearray(base64.b64decode(encrypted_text))
    key_byte = ord(key)  # 使用单个字符作为密钥

    # 对每个字节进行按位异或操作以解密
    decrypted_bytes = bytearray([b ^ key_byte for b in encrypted_bytes])

    # 将解密后的字节数组转换为字符串
    decrypted_text = decrypted_bytes.decode('utf-8')
    return decrypted_text


server_hosts = ['47.100.253.200:8000']

server_urls = [
    f"http://{address}/data/export/json?st=2024-01-01T00:00:00&et=2024-12-31T23:59:59" for address in server_hosts
]

# 加密User-Agent
key = 'H'
user_agent = "Yihsoft_Uenc"
encrypted_user_agent = encrypt(user_agent, key)
print(encrypted_user_agent)
# 持久连接
session = requests.Session()
session.headers.update({
    "User-Agent": encrypted_user_agent
})


def save_to_db(db, result):
    try:
        # 检查 result 是否包含 'data' 键
        if 'data' in result:
            data_list = result['data']
            for data in data_list:
                # 去除不在模型中的字段
                if 'id' in data:
                    del data['id']

                # 创建新的 UencVoiaem 实例并保存到数据库
                new_record = UencVoiaem(**data)
                db.add(new_record)

            db.commit()
            print(f"保存了 {len(data_list)} 条数据到数据库")
        else:
            print("没有数据需要保存")
    except Exception as e:
        db.rollback()  # 如果发生错误，回滚事务
        print(f"Error saving data to DB: {e}")


def make_request(session, url):
    """
    发送请求并返回结果
    :param session: requests会话对象
    :param url: 请求的URL
    :return: 解析后的数据或None
    """
    try:
        response = session.get(url)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Failed to fetch data from {url}, status code: {response.status_code}")
    except requests.ConnectionError as e:
        print(f"Connection error for {url}: {e}")
    return None


def sync_start():
    """
    开始同步，从多个服务器URL请求数据并保存到数据库
    :param server_urls: 服务器URL列表
    :return: 同步结果信息
    """

    with ThreadPoolExecutor(max_workers=len(server_urls)) as executor:
        futures = {executor.submit(make_request, session, url): url for url in server_urls}
        count = 0
        db = next(get_db())

        for future in futures:
            result = future.result()
            if result:
                save_to_db(db, result)
                count += 1

    print(f"共处理 {count} 次请求")

# # 调用同步函数
# sync_start()
