import asyncio
import json
import os
import shutil
from datetime import datetime, timezone, timedelta
import zipfile

import aiofiles
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import cmd_arg
import config
from main import CrawlerFactory
from tools import utils
from media_platform.xhs import XiaoHongShuCrawler
from store.xhs import XhsJsonStoreImplement
from utils.common_utils import delete_folder_contents, delete_local_file, extract_zip_to_folder
from utils.oss_utils import init_oss, upload_local_file_to_oss, download_file_from_oss

app = FastAPI()

# 爬虫是否在执行
CRAWLER_RUNNING = False
CRAWLER_RUNNING_TASK_ID = -1


class CrawlerTaskInfo(BaseModel):
    taskId: Optional[int] = None
    creatorIds: List[str]
    headless: Optional[bool] = False


class XhsLoginInfo(BaseModel):
    headless: Optional[bool] = False
    downloadFromOss: Optional[bool] = False
    uploadToOss: Optional[bool] = False


# 校验小红书登录状态
@app.post("/api/xhs/check_login")
async def check_login_status(login_info: XhsLoginInfo):
    utils.logger.info(f"检查小红书登录状态 login_info: {login_info}")
    config.PLATFORM = "xhs"
    config.LOGIN_TYPE = "qrcode"
    config.CRAWLER_TYPE = "creator"
    config.HEADLESS = login_info.headless
    try:
        # 从OSS上下载登录态
        if login_info.downloadFromOss:
            local_dir = os.path.join(os.getcwd(), "browser_data")
            delete_folder_contents(local_dir, remain_folder=True)
            # 下载 ZIP 文件到本地
            oss_file_path = "xhs/xhs_user_data_dir.zip"
            local_zip_path = os.path.join(local_dir, "xhs_user_data_dir.zip")
            download_success, _ = download_file_from_oss(oss_file_path, local_zip_path)
            # 解压 ZIP 文件
            if download_success:
                extract_zip_to_folder(local_zip_path, os.path.join(local_dir, "xhs_user_data_dir"))

        crawler = XiaoHongShuCrawler()
        login_success = await crawler.check_login_status()

        # 上传登录态信息到OSS
        if login_success and login_info.uploadToOss:
            dir_name = config.USER_DATA_DIR % "xhs"
            user_data_dir = os.path.join(os.getcwd(), "browser_data", dir_name)
            # 将目录打包成 ZIP 文件
            zip_file_path = shutil.make_archive(user_data_dir, 'zip', user_data_dir)
            oss_file_path = "xhs/xhs_user_data_dir.zip"
            utils.logger.info(
                f"小红书登录成功，将登录态数据上传到OSS，本地zip_file:{zip_file_path}, OSS路径：{oss_file_path}")
            upload_local_file_to_oss(zip_file_path, oss_file_path)
            delete_local_file(zip_file_path)

        return {
            "code": 0,
            "msg": "登录有效" if login_success else "登录无效",
            "data": login_success
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
    utils.logger.info(f"小红书登录 login_info: {login_info}")
    config.PLATFORM = "xhs"
    config.LOGIN_TYPE = "qrcode"
    config.CRAWLER_TYPE = "creator"
    config.HEADLESS = login_info.headless

    try:
        crawler = XiaoHongShuCrawler()
        await crawler.login()

        # 上传登录信息到OSS
        if login_info.uploadToOss:
            user_data_dir = os.path.join(os.getcwd(), "browser_data",
                                         config.USER_DATA_DIR % "xhs")
            # 将目录打包成 ZIP 文件
            zip_file_path = shutil.make_archive(user_data_dir, 'zip', user_data_dir)
            oss_file_path = f"xhs/{user_data_dir}.zip"
            utils.logger.info(
                f"小红书登录成功，将登录态数据上传到OSS，本地zip_file:{zip_file_path}, OSS路径：{oss_file_path}")
            upload_local_file_to_oss(zip_file_path, oss_file_path)

        return {
            "code": 0,
            "msg": "登录成功",
            "data": None
        }
    except Exception as e:
        utils.logger.error(f"小红书登录失败: {e}")
        return {
            "code": 1,
            "msg": str(e),
            "data": None
        }


# 获取爬取数据
@app.post("/api/xhs/crawler")
async def handle_crawler_request(task_info: CrawlerTaskInfo):
    global CRAWLER_RUNNING, CRAWLER_RUNNING_TASK_ID
    utils.logger.info(f"执行小红书数据爬取任务：task_info: {task_info}")
    if CRAWLER_RUNNING:
        msg = f"当前有任务正在执行，任务ID:{CRAWLER_RUNNING_TASK_ID}，请稍后再试!"
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
    utils.logger.info(f"本次需要爬取的小红书账号个数: {len(task_info.creatorIds)}")
    try:
        CRAWLER_RUNNING = True
        CRAWLER_RUNNING_TASK_ID = task_info.taskId
        # override config
        config.PLATFORM = "xhs"
        config.LOGIN_TYPE = "qrcode"
        config.CRAWLER_TYPE = "creator"
        config.HEADLESS = task_info.headless
        config.XHS_CREATOR_ID_LIST = task_info.creatorIds
        config.XHS_CREATOR_ERROR_USER_INFO = {}

        # 清除已有的json文件
        save_file_name = os.path.join(os.getcwd(), f"data/xhs/json/creator_contents_{utils.get_current_date()}.json")
        if os.path.exists(save_file_name):
            # 删除文件
            os.remove(save_file_name)

        # 开启抓取任务
        crawler = CrawlerFactory.create_crawler(platform=config.PLATFORM)
        await crawler.start()

        # 读取抓取的内容
        note_infos = []
        if os.path.exists(save_file_name):
            async with aiofiles.open(save_file_name, 'r', encoding='utf-8') as file:
                save_data = json.loads(await file.read())
            # 按note_id 去重
            seen_ids = set()
            for note in save_data:
                note_id = note["note_id"]
                if note_id not in seen_ids:
                    seen_ids.add(note_id)
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

        utils.logger.info(f"小红书数据爬取完毕, 获取笔记总数：{len(note_infos)}")
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
    except Exception as e:
        CRAWLER_RUNNING = False
        utils.logger.error(f"小红书数据爬取失败: {e}")
        return {
            "code": 1,
            "msg": str(e),
            "data": None
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
    uvicorn.run(app, host="127.0.0.1", port=11086, timeout_keep_alive=7200, lifespan='on')
