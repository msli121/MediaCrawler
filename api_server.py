import json
import os
import shutil
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import aiofiles
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

import cmd_arg
import config
from main import CrawlerFactory
from media_platform.xhs import XiaoHongShuCrawler
from tools import utils
from utils.common_utils import delete_folder_contents, delete_local_file, extract_zip_to_folder
from utils.oss_utils import upload_local_file_to_oss, download_file_from_oss

app = FastAPI()

# 爬虫是否在执行
CRAWLER_RUNNING = False
CRAWLER_RUNNING_XHS_USERNAME = ""
CRAWLER_RUNNING_TASK_ID = -1

# 小红书账号登录状态
XHS_ACCOUNT_INFO = []


class CrawlerTaskInfo(BaseModel):
    taskId: Optional[int] = None
    creatorIds: List[str]
    headless: Optional[bool] = False


class XhsLoginInfo(BaseModel):
    headless: Optional[bool] = False
    username: Optional[str] = None
    downloadFromOss: Optional[bool] = False
    uploadToOss: Optional[bool] = False


# 校验小红书登录状态
@app.post("/api/xhs/check_login")
async def check_login_status(login_info: XhsLoginInfo):
    global XHS_ACCOUNT_INFO
    utils.logger.info(f"检查小红书登录状态 login_info: {login_info}")
    config.PLATFORM = "xhs"
    config.LOGIN_TYPE = "qrcode"
    config.CRAWLER_TYPE = "creator"
    config.HEADLESS = login_info.headless
    XHS_ACCOUNT_INFO = []
    try:
        # 获取 browser_data目录下所有的文件夹
        folders = [f for f in os.listdir("./browser_data") if os.path.isdir(os.path.join("./browser_data", f))]
        # 遍历文件夹
        for folder in folders:
            # 打印文件夹名
            utils.logger.info(f"folder: {folder}")
            # 去掉文件夹名中开头的 "xhs_"前缀
            if folder.startswith("xhs_"):
                # 获取用户名
                username = folder[4:]
                # 校验登录信息
                crawler = XiaoHongShuCrawler()
                crawler.set_username(username)
                utils.logger.info(f"开始校验 {username} 的登录状态")
                try:
                    login_success = await crawler.check_login_status()
                    utils.logger.info(f"{username} 登录成功: {login_success}")
                except Exception as e:
                    utils.logger.error(f"校验 {username} 的登录状态失败: {e}")
                    login_success = False
                XHS_ACCOUNT_INFO.append({
                    "username": username,
                    "login_success": login_success
                })
        return {
            "code": 0,
            "msg": "处理完成",
            "data": XHS_ACCOUNT_INFO
        }
    except Exception as e:
        utils.logger.error(f"检查小红书登录状态失败: {e}")
        return {
            "code": 1,
            "msg": str(e),
            "data": False
        }


# 小红书登录
@app.post("/api/xhs/login")
async def login(login_info: XhsLoginInfo):
    global XHS_ACCOUNT_INFO
    utils.logger.info(f"小红书登录 login_info: {login_info}")
    config.PLATFORM = "xhs"
    config.LOGIN_TYPE = "qrcode"
    config.CRAWLER_TYPE = "creator"
    config.HEADLESS = login_info.headless

    username = login_info.username
    if username is None or username.strip() == '':
        username = "user_data_dir"

    selected_login_info = None
    if len(XHS_ACCOUNT_INFO) > 0:
        for account_info in XHS_ACCOUNT_INFO:
            if account_info['username'] == username:
                selected_login_info = account_info
                break

    try:
        crawler = XiaoHongShuCrawler()
        crawler.set_username(username)
        # 登录
        await crawler.login()
        if selected_login_info is None:
            selected_login_info = {
                'username': username,
                'login_success': True
            }
            XHS_ACCOUNT_INFO.append(selected_login_info)
        else:
            selected_login_info['login_success'] = True
        utils.logger.info(f"小红书登录成功，登录信息：{selected_login_info}")
        return {
            "code": 0,
            "msg": "登录成功",
            "data": f"{username} 登录成功"
        }
    except Exception as e:
        if selected_login_info is None:
            selected_login_info = {
                'username': username,
                'login_success': False
            }
            XHS_ACCOUNT_INFO.append(selected_login_info)
        else:
            selected_login_info['login_success'] = False
        utils.logger.error(f"小红书登录失败: {e}")
        return {
            "code": 1,
            "msg": str(e),
            "data": None
        }


# 获取爬取数据
@app.post("/api/xhs/crawler")
async def handle_crawler_request(task_info: CrawlerTaskInfo):
    global CRAWLER_RUNNING, CRAWLER_RUNNING_TASK_ID, CRAWLER_RUNNING_XHS_USERNAME
    start_time = time.time()
    utils.logger.info(f"【执行小红书数据爬取任务】task_info: {task_info}")
    if CRAWLER_RUNNING:
        msg = f"当前有任务正在执行，任务ID:{CRAWLER_RUNNING_TASK_ID}, 用户名：{CRAWLER_RUNNING_XHS_USERNAME}，请稍后再试!"
        utils.logger.warn(msg)
        return {
            "code": 1,
            "msg": msg,
            "data": None
        }
    if task_info.creatorIds is None or len(task_info.creatorIds) == 0:
        return {
            "code": 1,
            "msg": "creator_ids不能为空",
            "data": None
        }
    # 筛选出登录状态有效的小红书账号
    valid_login_infos = [login_info for login_info in XHS_ACCOUNT_INFO if login_info['login_success']]
    if len(valid_login_infos) == 0:
        return {
            "code": 1,
            "msg": "没有可用的小红书登录账号",
            "data": None
        }
    utils.logger.info(
        f"【执行小红书数据爬取任务】有效的小红书账号数：{len(valid_login_infos)}, 待抓取的账号数：{len(task_info.creatorIds)}")
    headless = task_info.headless
    # 保存抓取到的内容
    note_infos = []
    # 按note_id 去重
    note_ids = set()

    batch_size = 5
    # 将creatorIds分成多个批次，每个批次最多20个
    for i in range(0, len(task_info.creatorIds), batch_size):
        # 本批次处理的creatorIds
        creator_ids = task_info.creatorIds[i:i + batch_size]
        selected_index = 0
        for index, login_info in enumerate(valid_login_infos):
            if login_info['username'] == CRAWLER_RUNNING_XHS_USERNAME:
                selected_index = index
                break
        # 轮流使用可用的小红书账号
        selected_index = (selected_index + 1) % len(valid_login_infos)
        selected_username = valid_login_infos[selected_index]['username']
        utils.logger.info(
            f"【小红书数据爬取】正在处理第{i // batch_size + 1}批，共{len(task_info.creatorIds) // batch_size}批，本批使用的登录账号：{selected_username}，本批待抓取的账号个数:{len(creator_ids)}，待抓取的账号ID:{creator_ids}")
        try:
            CRAWLER_RUNNING = True
            CRAWLER_RUNNING_TASK_ID = task_info.taskId
            CRAWLER_RUNNING_XHS_USERNAME = selected_username
            # override config
            config.PLATFORM = "xhs"
            config.LOGIN_TYPE = "qrcode"
            config.CRAWLER_TYPE = "creator"
            config.HEADLESS = headless
            config.XHS_CREATOR_ID_LIST = creator_ids
            config.XHS_CREATOR_ERROR_USER_INFO = {}
            # 清除已有的json文件
            save_file_name = os.path.join(os.getcwd(),
                                          f"data/xhs/json/creator_contents_{utils.get_current_date()}.json")
            if os.path.exists(save_file_name):
                # 删除文件
                os.remove(save_file_name)
            # 开启抓取任务
            crawler = XiaoHongShuCrawler()
            crawler.set_username(selected_username)
            await crawler.start()
            # 读取json文件数据
            if os.path.exists(save_file_name):
                async with aiofiles.open(save_file_name, 'r', encoding='utf-8') as file:
                    save_data = json.loads(await file.read())
                # 按note_id 去重
                for note in save_data:
                    note_id = note["note_id"]
                    if note_id not in note_ids:
                        note_ids.add(note_id)
                        note_info = {
                            "noteId": note["note_id"],
                            "noteTitle": note["title"],
                            "noteUrl": note["note_url"],
                            "notePublishTime": timestamp_to_beijing_time(note["time"]),
                            "kolId": note["user_id"],
                            "likeNum": note["liked_count"],
                            "favNum": note["collected_count"],
                            "cmtNum": note["comment_count"],
                            "shareNum": note["share_count"],
                        }
                        note_infos.append(note_info)
        except Exception as e:
            CRAWLER_RUNNING = False
            utils.logger.error(f"小红书数据爬取失败: {e}")
            continue
    end_time = time.time()
    elapsed_time = end_time - start_time
    # 计算小时、分钟和秒
    hours = int(elapsed_time // 3600)
    minutes = int((elapsed_time % 3600) // 60)
    seconds = int(elapsed_time % 60)
    utils.logger.info(
        f"【小红书数据爬取完毕】有效登录的小红书账号数：{len(valid_login_infos)}, 抓取数据的小红书账号数：{len(task_info.creatorIds)}，获取笔记总数：{len(note_infos)}, 总耗时：{hours}时{minutes}分{seconds}秒")
    CRAWLER_RUNNING = False
    return {
        "code": 0,
        "msg": "小红书数据爬取完成",
        "data": {
            "total": len(note_infos),
            "list": note_infos,
            "errorInfos": config.XHS_CREATOR_ERROR_USER_INFO
        }
    }


# 时间戳转换为北京时间
def timestamp_to_beijing_time(timestamp: int) -> str:
    """
    将时间戳转换为北京时间，并格式化为指定的日期时间字符串。
    该方法能够处理以毫秒和秒为单位的时间戳。

    :param timestamp: 时间戳（毫秒或秒）
    :return: 格式化的北京时间字符串
    """
    # 判断时间戳的单位（毫秒或秒）
    if timestamp > 1e10:  # 长度大于10位，认为是毫秒
        timestamp_seconds = timestamp / 1000
    else:  # 否则认为是秒
        timestamp_seconds = timestamp

    # 创建 UTC 时间的 datetime 对象
    utc_time = datetime.fromtimestamp(timestamp_seconds, tz=timezone.utc)

    # 将 UTC 时间转换为北京时间
    beijing_time = utc_time + timedelta(hours=8)

    # 格式化为指定的日期时间字符串
    formatted_time = beijing_time.strftime('%Y-%m-%d %H:%M:%S')

    return formatted_time


# 启动服务
if __name__ == "__main__":
    # parse cmd
    cmd_arg.parse_cmd()
    # init oss
    # init_oss(access_key_id=config.OSS_ACCESS_KEY_ID, access_key_secret=config.OSS_ACCESS_KEY_SECRET)
    # 启动应用
    uvicorn.run(app, host="0.0.0.0", port=11086, timeout_keep_alive=7200, lifespan='on')

# # 从OSS上下载登录态
# if login_info.downloadFromOss:
#     local_dir = os.path.join(os.getcwd(), "browser_data")
#     delete_folder_contents(local_dir, remain_folder=True)
#     # 下载 ZIP 文件到本地
#     oss_file_path = "xhs/xhs_user_data_dir.zip"
#     local_zip_path = os.path.join(local_dir, "xhs_user_data_dir.zip")
#     download_success, _ = download_file_from_oss(oss_file_path, local_zip_path)
#     # 解压 ZIP 文件
#     if download_success:
#         extract_zip_to_folder(local_zip_path, os.path.join(local_dir, "xhs_user_data_dir"))
# # 上传登录态信息到OSS
# if login_success and login_info.uploadToOss:
#     dir_name = config.USER_DATA_DIR % "xhs"
#     user_data_dir = os.path.join(os.getcwd(), "browser_data", dir_name)
#     # 将目录打包成 ZIP 文件
#     zip_file_path = shutil.make_archive(user_data_dir, 'zip', user_data_dir)
#     oss_file_path = "xhs/xhs_user_data_dir.zip"
#     utils.logger.info(
#         f"小红书登录成功，将登录态数据上传到OSS，本地zip_file:{zip_file_path}, OSS路径：{oss_file_path}")
#     upload_local_file_to_oss(zip_file_path, oss_file_path)
#     delete_local_file(zip_file_path)
