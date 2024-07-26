import datetime
import os
import random
import shutil
import string
import zipfile
from pathlib import Path


def extract_zip_to_folder(zip_path, extract_to):
    """
    解压 ZIP 文件并将内容保存到指定文件夹下，保留文件夹结构
    """
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        for member in zip_ref.namelist():
            # 计算解压后的路径
            extracted_path = os.path.join(extract_to, member)
            # 创建父文件夹（如果不存在）
            os.makedirs(os.path.dirname(extracted_path), exist_ok=True)
            # 提取文件
            zip_ref.extract(member, extract_to)
    print(f"Extracted {zip_path} to {extract_to}")


# 删除整个文件夹
def delete_folder_contents(folder_path, remain_folder=False):
    """
    删除整个文件夹内容，但根据 remain_folder 参数选择是否保留文件夹本身
    """
    # 检查文件夹是否存在
    if os.path.exists(folder_path):
        # 删除文件夹下的所有文件和子文件夹
        for item in os.listdir(folder_path):
            item_path = os.path.join(folder_path, item)
            if os.path.isfile(item_path) or os.path.islink(item_path):
                os.unlink(item_path)  # 删除文件或符号链接
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)  # 删除子文件夹及其内容
        if not remain_folder:
            # 删除文件夹本身
            os.rmdir(folder_path)
        print(f"Cleared contents of the folder: {folder_path}")
    else:
        print(f"Folder does not exist: {folder_path}")


def delete_local_file(file_path):
    # 检查文件夹是否存在
    if os.path.exists(file_path):
        # 删除文件夹及其所有内容
        os.remove(file_path)
        print(f"Deleted file: {file_path}")
    else:
        print(f"File does not exist: {file_path}")


def is_video_url(url_or_path):
    """
    判断给定的URL地址或者OSS路径是否为视频类型的地址。

    :param url_or_path: URL地址或者OSS路径字符串
    :return: 如果是视频类型的地址返回True，否则返回False
    """
    video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv']
    url_path = url_or_path.lower()  # 将路径转换为小写

    for ext in video_extensions:
        if ext in url_path:
            return True

    return False


def is_image_url(url_or_path):
    """
    判断给定的URL地址或者OSS路径是否为图片类型的地址。

    :param url_or_path: URL地址或者OSS路径字符串
    :return: 如果是图片类型的地址返回True，否则返回False
    """
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp']
    url_path = url_or_path.lower()  # 将路径转换为小写

    for ext in image_extensions:
        if ext in url_path:
            return True

    return False


# 随机生成指定长度的字符串
def generate_random_string(length=6):
    # Define the possible characters: uppercase, lowercase letters and digits
    characters = string.ascii_letters + string.digits
    # Generate a random string
    random_string = ''.join(random.choices(characters, k=length))
    return random_string


# 获取当前日期字符串，格式为YYYYMMDD
def get_current_day_str():
    return datetime.datetime.now().strftime("%Y%m%d")


# 随机生成指定长度的字符串，并添加日期前缀
def generate_random_string_with_day_prefix(length=6):
    # 当前日期对应的字符串
    current_date_str = get_current_day_str()
    return current_date_str + '_' + generate_random_string(length=length)


# 校验指定文件地址对应文件是否存在，不存在则新建文件
def check_file_exist(file_path, need_new=False):
    if not Path(file_path).exists():
        if need_new:
            dir_name = os.path.dirname(file_path)
            if not os.path.exists(dir_name):
                os.makedirs(dir_name)
        return False
    return True
