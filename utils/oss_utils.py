import re
import os

import oss2
from enum import Enum

bucket = None


class OssOperationType(Enum):
    GET = 'GET'
    PUT = 'PUT'


# 初始化OSS配置
def init_oss(access_key_id, access_key_secret, endpoint='https://oss-cn-shanghai.aliyuncs.com',
             bucket_name='iaimarket-utils'):
    # 初始化OSS配置
    global bucket
    auth = oss2.Auth(access_key_id, access_key_secret)
    bucket = oss2.Bucket(auth, endpoint, bucket_name)
    print("OSS初始化完成")


def upload_local_file_to_oss(local_file_path, oss_file_path):
    try:
        # 上传文件
        bucket.put_object_from_file(oss_file_path, local_file_path)
        print(f"文件 {local_file_path} 成功上传到 OSS 路径 {oss_file_path}")
        return True, "success"
    except Exception as e:
        # 处理上传异常
        print(f"上传文件到OSS失败：{e}")
        return False, f"上传文件到OSS失败：{e}"


def download_file_from_oss(oss_file_path, local_file_path):
    """
    从OSS下载对象到本地文件
    Args:
        oss_file_path: OSS对象路径
        local_file_path: 本地文件路径
    Returns:
        Tuple: (成功标志, 消息)
    """
    try:
        # 创建本地文件夹（如果不存在）
        local_dir = os.path.dirname(local_file_path)
        if not os.path.exists(local_dir):
            os.makedirs(local_dir)

        # 处理OSS文件路径
        oss_file_path = process_url(oss_file_path)

        # 下载文件
        bucket.get_object_to_file(oss_file_path, local_file_path)
        print(f"文件 {oss_file_path} 成功下载到本地路径 {local_file_path}")
        return True, "success"
    except Exception as e:
        # 处理下载异常
        print(f"从OSS下载文件失败：{e}")
        return False, f"从OSS下载文件失败：{e}"


def generate_get_url(oss_file_path, expiration=3600):
    """
    生成可以在公网访问的HTTPS链接
    :param oss_file_path: OSS文件路径
    :param expiration: 链接有效期（秒），默认3600秒
    :return: 生成的URL
    """
    try:
        if oss_file_path is None or oss_file_path == "":
            return ""
        # 处理OSS文件路径
        oss_file_path = process_url(oss_file_path)
        # 生成签名URL
        url = bucket.sign_url('GET', oss_file_path, expiration, slash_safe=True)
        # 将URL中的编码斜杠替换回斜杠
        url = url.replace('%2F', '/')
        # print(f"[generate_get_url] 生成的URL为：{url}")
        return url
    except Exception as e:
        # 处理生成URL异常
        print(f"生成公有链接失败：{e}")
        return None


def get_oss_paths(file_path_dir, max_keys=9):
    """
    按OSS对象创建时间的倒序，获取指定OSS目录下的文件列表，并生成对应的URL

    Args:
        file_path_dir (str): OSS目录路径
        max_keys (int): 最大返回的文件数量

    Returns:
        dict: 包含图片URL的List
    """
    keys = []
    for obj in bucket.list_objects(file_path_dir, delimiter='/').object_list:
        keys.append(obj.key)
        if len(keys) >= max_keys:
            break

    # 获取文件的元数据来排序
    keys_with_meta = []
    for key in keys:
        meta = bucket.head_object(key)
        keys_with_meta.append((key, meta.last_modified))

    # 按元数据中的last_modified时间倒序排序
    keys_with_meta.sort(key=lambda x: x[1], reverse=True)

    # 获取排序后的文件URL
    image_urls = [generate_get_url(key) for key, _ in keys_with_meta[:max_keys]]

    return image_urls


def process_url(url):
    if not url:
        return ""

    # 去除域名前缀
    if url.startswith("http"):
        url = re.sub(r"https?://[^/]+/", "/", url)

    # 去除 ? 及其后面的部分
    query_string_index = url.find('?')
    if query_string_index != -1:
        url = url[:query_string_index]

    # 去掉开头的/
    if url.startswith("/"):
        url = url[1:]

    return url


# 获取指定前缀下的最近n个文件
def list_recent_files(prefix, max_keys=9):
    """
    获取指定前缀下的最近n个文件
    Args:
        prefix:
        max_keys:
    Returns:
    """
    # 列出文件并按上传时间排序
    files = []
    for obj in oss2.ObjectIterator(bucket, prefix=prefix):
        files.append({
            'key': obj.key,
            'last_modified': obj.last_modified
        })

    # 按最后修改时间降序排序
    files.sort(key=lambda x: x['last_modified'], reverse=True)

    # 取最近的max_files个文件
    recent_files = files[:max_keys]

    # 获取排序后的文件URL
    image_urls = [generate_get_url(item['key']) for item in recent_files]

    return image_urls
