import base64
import time
from concurrent.futures import ThreadPoolExecutor
import requests


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


# 服务地址
base_url = "http://47.100.253.200:8000/data/export/json?st=2024-01-01T00:00:00&et=2024-12-31T23:59:59"

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


def make_request(session):
    response = session.get(base_url)
    if response.status_code == 200:
        print(f"Response Body: {response.json()}")
        remaining_count = response.json().get("remaining_count")
        return remaining_count
    return None


def sync_start():
    """
    开始同步
    :return:
    """
    start_time = time.time()
    count = 0
    with ThreadPoolExecutor(max_workers=10) as executor:
        while True:
            count += 1
            future = executor.submit(make_request, session)
            remaining_count = future.result()
            print(f"Remaining Count: {remaining_count}")
            if remaining_count == 0 or remaining_count is None:
                break

    end_time = time.time()
    elapsed_time = (end_time - start_time) * 1000
    return f"耗时 {elapsed_time:.4f} 毫秒,共{count}次请求"
