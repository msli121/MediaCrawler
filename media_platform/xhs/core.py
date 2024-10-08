import asyncio
import os
import random
from asyncio import Task
from typing import Dict, List, Optional, Tuple

from playwright.async_api import (BrowserContext, BrowserType, Page,
                                  async_playwright)
from tenacity import RetryError

import config
from base.base_crawler import AbstractCrawler
from proxy.proxy_ip_pool import IpInfoModel, create_ip_pool
from store import xhs as xhs_store
from tools import utils
from var import crawler_type_var, source_keyword_var

from .client import XiaoHongShuClient
from .exception import DataFetchError
from .field import SearchSortType
from .login import XiaoHongShuLogin


class XiaoHongShuCrawler(AbstractCrawler):
    context_page: Page
    xhs_client: XiaoHongShuClient
    browser_context: BrowserContext

    def __init__(self) -> None:
        self.username = "user_data_dir"
        self.index_url = "https://www.xiaohongshu.com"
        # self.user_agent = utils.get_user_agent()
        self.user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

    def set_username(self, username: str):
        self.username = username

    # 校验登录状态
    async def check_login_status(self) -> bool:
        playwright_proxy_format, httpx_proxy_format = None, None
        if config.ENABLE_IP_PROXY:
            ip_proxy_pool = await create_ip_pool(config.IP_PROXY_POOL_COUNT, enable_validate_ip=True)
            ip_proxy_info: IpInfoModel = await ip_proxy_pool.get_proxy()
            playwright_proxy_format, httpx_proxy_format = self.format_proxy_info(ip_proxy_info)
        try:
            async with async_playwright() as playwright:
                # Launch a browser context.
                chromium = playwright.chromium
                self.browser_context = await self.launch_browser(
                    chromium,
                    None,
                    self.user_agent,
                    headless=config.HEADLESS,
                    username=self.username,
                )
                # stealth.min.js is a js script to prevent the website from detecting the crawler.
                await self.browser_context.add_init_script(path="libs/stealth.min.js")
                # add a cookie attribute webId to avoid the appearance of a sliding captcha on the webpage
                await self.browser_context.add_cookies([{
                    'name': "webId",
                    'value': "xxx123",  # any value
                    'domain': ".xiaohongshu.com",
                    'path': "/"
                }])
                self.context_page = await self.browser_context.new_page()
                await self.context_page.goto(self.index_url)

                # Create a client to interact with the xiaohongshu website.
                self.xhs_client = await self.create_xhs_client(httpx_proxy_format)
                return await self.xhs_client.pong()
        except Exception as e:
            utils.logger.error(f"Check login status failed: {e}")
            return False

    # 开始登录
    async def login(self) -> None:
        playwright_proxy_format, httpx_proxy_format = None, None
        if config.ENABLE_IP_PROXY:
            ip_proxy_pool = await create_ip_pool(config.IP_PROXY_POOL_COUNT, enable_validate_ip=True)
            ip_proxy_info: IpInfoModel = await ip_proxy_pool.get_proxy()
            playwright_proxy_format, httpx_proxy_format = self.format_proxy_info(ip_proxy_info)
        async with async_playwright() as playwright:
            # Launch a browser context.
            chromium = playwright.chromium
            self.browser_context = await self.launch_browser(
                chromium,
                None,
                self.user_agent,
                headless=config.HEADLESS,
                username=self.username,
            )
            # stealth.min.js is a js script to prevent the website from detecting the crawler.
            await self.browser_context.add_init_script(path="libs/stealth.min.js")
            # add a cookie attribute webId to avoid the appearance of a sliding captcha on the webpage
            await self.browser_context.add_cookies([{
                'name': "webId",
                'value': self.username,  # any value
                'domain': ".xiaohongshu.com",
                'path': "/"
            }])
            self.context_page = await self.browser_context.new_page()
            await self.context_page.goto(self.index_url, timeout=60000)

            # Create a client to interact with the xiaohongshu website.
            self.xhs_client = await self.create_xhs_client(httpx_proxy_format)
            if not await self.xhs_client.pong():
                login_obj = XiaoHongShuLogin(
                    login_type=config.LOGIN_TYPE,
                    login_phone="",  # input your phone number
                    browser_context=self.browser_context,
                    context_page=self.context_page,
                    cookie_str=config.COOKIES
                )
                await login_obj.begin()
                await self.xhs_client.update_cookies(browser_context=self.browser_context)

    # 打开页面最多停留5min
    async def open_web(self) -> None:
        playwright_proxy_format, httpx_proxy_format = None, None
        if config.ENABLE_IP_PROXY:
            ip_proxy_pool = await create_ip_pool(config.IP_PROXY_POOL_COUNT, enable_validate_ip=True)
            ip_proxy_info: IpInfoModel = await ip_proxy_pool.get_proxy()
            playwright_proxy_format, httpx_proxy_format = self.format_proxy_info(ip_proxy_info)
        async with async_playwright() as playwright:
            # Launch a browser context.
            chromium = playwright.chromium
            self.browser_context = await self.launch_browser(
                chromium,
                None,
                self.user_agent,
                headless=config.HEADLESS,
                username=self.username,
            )
            # stealth.min.js is a js script to prevent the website from detecting the crawler.
            await self.browser_context.add_init_script(path="libs/stealth.min.js")
            # add a cookie attribute webId to avoid the appearance of a sliding captcha on the webpage
            await self.browser_context.add_cookies([{
                'name': "webId",
                'value': self.username,  # any value
                'domain': ".xiaohongshu.com",
                'path': "/"
            }])
            self.context_page = await self.browser_context.new_page()
            await self.context_page.goto(self.index_url, timeout=60000)
            # todo 打开页面最多停留5min，如果关闭了浏览器则直接退出
            max_wait_time = 5 * 60  # 5 minutes in seconds
            check_interval = 2  # Check every 10 seconds
            time_waited = 0
            while time_waited < max_wait_time:
                if self.context_page.is_closed():
                    utils.logger.info("Browser closed. Exiting.")
                    return
                await asyncio.sleep(check_interval)
                time_waited += check_interval
            utils.logger.info("Max wait time reached. Closing browser.")
            await self.browser_context.close()

    async def start(self) -> None:
        playwright_proxy_format, httpx_proxy_format = None, None
        if config.ENABLE_IP_PROXY:
            ip_proxy_pool = await create_ip_pool(config.IP_PROXY_POOL_COUNT, enable_validate_ip=True)
            ip_proxy_info: IpInfoModel = await ip_proxy_pool.get_proxy()
            playwright_proxy_format, httpx_proxy_format = self.format_proxy_info(ip_proxy_info)

        async with async_playwright() as playwright:
            # Launch a browser context.
            chromium = playwright.chromium
            self.browser_context = await self.launch_browser(
                chromium,
                None,
                self.user_agent,
                headless=config.HEADLESS,
                username=self.username,
            )
            # stealth.min.js is a js script to prevent the website from detecting the crawler.
            await self.browser_context.add_init_script(path="libs/stealth.min.js")
            # add a cookie attribute webId to avoid the appearance of a sliding captcha on the webpage
            await self.browser_context.add_cookies([{
                'name': "webId",
                'value': "xxx123",  # any value
                'domain': ".xiaohongshu.com",
                'path': "/"
            }])
            self.context_page = await self.browser_context.new_page()
            await self.context_page.goto(self.index_url)

            # Create a client to interact with the xiaohongshu website.
            self.xhs_client = await self.create_xhs_client(httpx_proxy_format)
            if not await self.xhs_client.pong():
                login_obj = XiaoHongShuLogin(
                    login_type=config.LOGIN_TYPE,
                    login_phone="",  # input your phone number
                    browser_context=self.browser_context,
                    context_page=self.context_page,
                    cookie_str=config.COOKIES
                )
                await login_obj.begin()
                await self.xhs_client.update_cookies(browser_context=self.browser_context)

            crawler_type_var.set(config.CRAWLER_TYPE)
            if config.CRAWLER_TYPE == "search":
                # Search for notes and retrieve their comment information.
                await self.search()
            elif config.CRAWLER_TYPE == "detail":
                # Get the information and comments of the specified post
                await self.get_specified_notes()
            elif config.CRAWLER_TYPE == "creator":
                # Get creator's information and their notes and comments
                await self.get_creators_and_notes()
            else:
                pass

            utils.logger.info("[XiaoHongShuCrawler.start] Xhs Crawler finished ...")

    async def search(self) -> None:
        """Search for notes and retrieve their comment information."""
        utils.logger.info("[XiaoHongShuCrawler.search] Begin search xiaohongshu keywords")
        xhs_limit_count = 20  # xhs limit page fixed value
        if config.CRAWLER_MAX_NOTES_COUNT < xhs_limit_count:
            config.CRAWLER_MAX_NOTES_COUNT = xhs_limit_count
        start_page = config.START_PAGE
        for keyword in config.KEYWORDS.split(","):
            source_keyword_var.set(keyword)
            utils.logger.info(f"[XiaoHongShuCrawler.search] Current search keyword: {keyword}")
            page = 1
            while (page - start_page + 1) * xhs_limit_count <= config.CRAWLER_MAX_NOTES_COUNT:
                if page < start_page:
                    utils.logger.info(f"[XiaoHongShuCrawler.search] Skip page {page}")
                    page += 1
                    continue

                try:
                    utils.logger.info(f"[XiaoHongShuCrawler.search] search xhs keyword: {keyword}, page: {page}")
                    note_id_list: List[str] = []
                    notes_res = await self.xhs_client.get_note_by_keyword(
                        keyword=keyword,
                        page=page,
                        sort=SearchSortType(config.SORT_TYPE) if config.SORT_TYPE != '' else SearchSortType.GENERAL,
                    )
                    utils.logger.info(f"[XiaoHongShuCrawler.search] Search notes res:{notes_res}")
                    if not notes_res or not notes_res.get('has_more', False):
                        utils.logger.info("No more content!")
                        break
                    semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
                    task_list = [
                        self.get_note_detail_async_task(
                            note_id=post_item.get("id"),
                            xsec_source=post_item.get("xsec_source"),
                            xsec_token=post_item.get("xsec_token"),
                            semaphore=semaphore
                        )
                        for post_item in notes_res.get("items", {})
                        if post_item.get('model_type') not in ('rec_query', 'hot_query')
                    ]
                    note_details = await asyncio.gather(*task_list)
                    for note_detail in note_details:
                        if note_detail:
                            await xhs_store.update_xhs_note(note_detail)
                            await self.get_notice_media(note_detail)
                            note_id_list.append(note_detail.get("note_id"))
                    page += 1
                    utils.logger.info(f"[XiaoHongShuCrawler.search] Note details: {note_details}")
                    await self.batch_get_note_comments(note_id_list)
                except DataFetchError:
                    utils.logger.error("[XiaoHongShuCrawler.search] Get note detail error")
                    break

    async def get_creators_and_notes(self) -> None:
        """Get creator's notes and retrieve their comment information."""
        utils.logger.info("[XiaoHongShuCrawler.get_creators_and_notes] Begin get xiaohongshu creators")
        index = 1
        for user_id in config.XHS_CREATOR_ID_LIST:
            try:
                utils.logger.info(
                    f"[获取用户信息和笔记详情] 当前使用的小红书账号:{self.username}，正在处理第{index}个账号，本批共{len(config.XHS_CREATOR_ID_LIST)}个账号")
                index += 1
                # get creator detail info from web html content
                createor_info: Dict = await self.xhs_client.get_creator_info(user_id=user_id)
                if createor_info:
                    await xhs_store.save_creator(user_id, creator=createor_info)

                # Get all note information of the creator
                all_notes_list = await self.xhs_client.get_all_notes_by_creator(
                    user_id=user_id,
                    crawl_interval=random.random(),
                    callback=self.fetch_creator_notes_detail_sync
                )

                note_ids = [note_item.get("note_id") for note_item in all_notes_list]
                await self.batch_get_note_comments(note_ids)
            except Exception as e:
                utils.logger.error(f"[查询个人笔记失败] 登录账号：{self.username}, 查询账号: {user_id}, error: {e}")
                config.XHS_CREATOR_ERROR_USER_INFO[user_id] = str(e)

    async def fetch_creator_notes_detail_sync(self, note_list: List[Dict]):
        """同步获取笔记详情"""
        for post_item in note_list:
            note_detail = await self.get_note_detail_sync_task(
                note_id=post_item.get("note_id"),
                xsec_source=post_item.get("xsec_source"),
                xsec_token=post_item.get("xsec_token"),
            )
            if note_detail:
                await xhs_store.update_xhs_note(note_detail)

    async def fetch_creator_notes_detail(self, note_list: List[Dict]):
        """
        Concurrently obtain the specified post list and save the data
        """
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list = [
            self.get_note_detail_async_task(
                note_id=post_item.get("note_id"),
                xsec_source=post_item.get("xsec_source"),
                xsec_token=post_item.get("xsec_token"),
                semaphore=semaphore
            )
            for post_item in note_list
        ]

        note_details = await asyncio.gather(*task_list)
        for note_detail in note_details:
            if note_detail:
                await xhs_store.update_xhs_note(note_detail)

    async def get_specified_notes(self):
        """Get the information and comments of the specified post"""

        async def get_note_detail_from_html_task(note_id: str, semaphore: asyncio.Semaphore) -> Dict:
            async with semaphore:
                try:
                    _note_detail: Dict = await self.xhs_client.get_note_by_id_from_html(note_id)
                    if not _note_detail:
                        utils.logger.error(
                            f"[XiaoHongShuCrawler.get_note_detail_from_html] Get note detail error, note_id: {note_id}")
                        return {}
                    return _note_detail
                except DataFetchError as ex:
                    utils.logger.error(f"[XiaoHongShuCrawler.get_note_detail_from_html] Get note detail error: {ex}")
                    return {}
                except KeyError as ex:
                    utils.logger.error(
                        f"[XiaoHongShuCrawler.get_note_detail_from_html] have not fund note detail note_id:{note_id}, err: {ex}")
                    return {}
                except RetryError as ex:
                    utils.logger.error(
                        f"[XiaoHongShuCrawler.get_note_detail_from_html] Retry error, note_id:{note_id}, err: {ex}")

        get_note_detail_task_list = [
            get_note_detail_from_html_task(note_id=note_id, semaphore=asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)) for
            note_id in config.XHS_SPECIFIED_ID_LIST
        ]

        need_get_comment_note_ids = []
        note_details = await asyncio.gather(*get_note_detail_task_list)
        for note_detail in note_details:
            if note_detail:
                need_get_comment_note_ids.append(note_detail.get("note_id"))
                await xhs_store.update_xhs_note(note_detail)
        await self.batch_get_note_comments(need_get_comment_note_ids)

    # 同步获取获取笔记详情
    async def get_note_detail_sync_task(self, note_id: str, xsec_source: str, xsec_token: str) -> Optional[Dict]:
        try:
            # 随机使用html或者api获取笔记详情
            if random.random() > 0.5:
                note_detail: Dict = await self.xhs_client.get_note_by_id_from_html(note_id)
                if not note_detail:
                    note_detail: Dict = await self.xhs_client.get_note_by_id(note_id, xsec_source, xsec_token)
            else:
                note_detail: Dict = await self.xhs_client.get_note_by_id(note_id, xsec_source, xsec_token)
                if not note_detail:
                    note_detail: Dict = await self.xhs_client.get_note_by_id_from_html(note_id)

            if not note_detail:
                utils.logger.error(
                    f"[XiaoHongShuCrawler.get_note_detail_sync_task] Get note detail error, note_id: {note_id}")
                return None
            note_detail.update({"xsec_token": xsec_token, "xsec_source": xsec_source})
            return note_detail
        except DataFetchError as ex:
            utils.logger.error(f"[XiaoHongShuCrawler.get_note_detail_sync_task] Get note detail error: {ex}")
            return None
        except KeyError as ex:
            utils.logger.error(
                f"[XiaoHongShuCrawler.get_note_detail_sync_task] have not fund note detail note_id:{note_id}, err: {ex}")
            return None
        except Exception as e:
            utils.logger.error(f"[查询笔记详情失败] note_id:{note_id}, error: {e}")
            return None

    async def get_note_detail_async_task(self, note_id: str, xsec_source: str, xsec_token: str,
                                         semaphore: asyncio.Semaphore) -> \
            Optional[Dict]:
        """Get note detail"""
        async with semaphore:
            try:
                # note_detail: Dict = await self.xhs_client.get_note_by_id_from_html(note_id)
                note_detail: Dict = await self.xhs_client.get_note_by_id(note_id, xsec_source, xsec_token)
                if not note_detail:
                    utils.logger.error(
                        f"[XiaoHongShuCrawler.get_note_detail_async_task] Get note detail error, note_id: {note_id}")
                    return None
                note_detail.update({"xsec_token": xsec_token, "xsec_source": xsec_source})
                return note_detail
            except DataFetchError as ex:
                utils.logger.error(f"[XiaoHongShuCrawler.get_note_detail_async_task] Get note detail error: {ex}")
                return None
            except KeyError as ex:
                utils.logger.error(
                    f"[XiaoHongShuCrawler.get_note_detail_async_task] have not fund note detail note_id:{note_id}, err: {ex}")
                return None

    async def batch_get_note_comments(self, note_list: List[str]):
        """Batch get note comments"""
        if not config.ENABLE_GET_COMMENTS:
            utils.logger.info(f"[XiaoHongShuCrawler.batch_get_note_comments] Crawling comment mode is not enabled")
            return

        utils.logger.info(
            f"[XiaoHongShuCrawler.batch_get_note_comments] Begin batch get note comments, note list: {note_list}")
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list: List[Task] = []
        for note_id in note_list:
            task = asyncio.create_task(self.get_comments(note_id, semaphore), name=note_id)
            task_list.append(task)
        await asyncio.gather(*task_list)

    async def get_comments(self, note_id: str, semaphore: asyncio.Semaphore):
        """Get note comments with keyword filtering and quantity limitation"""
        async with semaphore:
            utils.logger.info(f"[XiaoHongShuCrawler.get_comments] Begin get note id comments {note_id}")
            await self.xhs_client.get_note_all_comments(
                note_id=note_id,
                crawl_interval=random.random(),
                callback=xhs_store.batch_update_xhs_note_comments
            )

    @staticmethod
    def format_proxy_info(ip_proxy_info: IpInfoModel) -> Tuple[Optional[Dict], Optional[Dict]]:
        """format proxy info for playwright and httpx"""
        playwright_proxy = {
            "server": f"{ip_proxy_info.protocol}{ip_proxy_info.ip}:{ip_proxy_info.port}",
            "username": ip_proxy_info.user,
            "password": ip_proxy_info.password,
        }
        httpx_proxy = {
            f"{ip_proxy_info.protocol}": f"http://{ip_proxy_info.user}:{ip_proxy_info.password}@{ip_proxy_info.ip}:{ip_proxy_info.port}"
        }
        return playwright_proxy, httpx_proxy

    async def create_xhs_client(self, httpx_proxy: Optional[str]) -> XiaoHongShuClient:
        """Create xhs client"""
        utils.logger.info("[XiaoHongShuCrawler.create_xhs_client] Begin create xiaohongshu API client ...")
        cookie_str, cookie_dict = utils.convert_cookies(await self.browser_context.cookies())
        xhs_client_obj = XiaoHongShuClient(
            proxies=httpx_proxy,
            headers={
                "User-Agent": self.user_agent,
                "Cookie": cookie_str,
                "Origin": "https://www.xiaohongshu.com",
                "Referer": "https://www.xiaohongshu.com",
                "Content-Type": "application/json;charset=UTF-8"
            },
            playwright_page=self.context_page,
            cookie_dict=cookie_dict,
        )
        return xhs_client_obj

    async def launch_browser(
            self,
            chromium: BrowserType,
            playwright_proxy: Optional[Dict],
            user_agent: Optional[str],
            headless: bool = True,
            username: Optional[str] = 'user_data_dir',
    ) -> BrowserContext:
        """Launch browser and create browser context"""
        utils.logger.info("[XiaoHongShuCrawler.launch_browser] Begin create browser context ...")
        if config.SAVE_LOGIN_STATE:
            # feat issue #14
            # we will save login state to avoid login every time
            user_data_dir = os.path.join(os.getcwd(), "browser_data",
                                         f"xhs_{username}")  # type: ignore
            browser_context = await chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                accept_downloads=True,
                headless=headless,
                proxy=playwright_proxy,  # type: ignore
                viewport={"width": 1920, "height": 1080},
                user_agent=user_agent
            )
            return browser_context
        else:
            browser = await chromium.launch(headless=headless, proxy=playwright_proxy)  # type: ignore
            browser_context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=user_agent
            )
            return browser_context

    async def close(self):
        """Close browser context"""
        await self.browser_context.close()
        utils.logger.info("[XiaoHongShuCrawler.close] Browser context closed ...")

    async def get_notice_media(self, note_detail: Dict):
        if not config.ENABLE_GET_IMAGES:
            utils.logger.info(f"[XiaoHongShuCrawler.get_notice_media] Crawling image mode is not enabled")
            return
        await self.get_note_images(note_detail)
        await self.get_notice_video(note_detail)

    async def get_note_images(self, note_item: Dict):
        """
        get note images. please use get_notice_media
        :param note_item:
        :return:
        """
        if not config.ENABLE_GET_IMAGES:
            return
        note_id = note_item.get("note_id")
        image_list: List[Dict] = note_item.get("image_list", [])

        for img in image_list:
            if img.get('url_default') != '':
                img.update({'url': img.get('url_default')})

        if not image_list:
            return
        picNum = 0
        for pic in image_list:
            url = pic.get("url")
            if not url:
                continue
            content = await self.xhs_client.get_note_media(url)
            if content is None:
                continue
            extension_file_name = f"{picNum}.jpg"
            picNum += 1
            await xhs_store.update_xhs_note_image(note_id, content, extension_file_name)

    async def get_notice_video(self, note_item: Dict):
        """
        get note images. please use get_notice_media
        :param note_item:
        :return:
        """
        if not config.ENABLE_GET_IMAGES:
            return
        note_id = note_item.get("note_id")

        videos = xhs_store.get_video_url_arr(note_item)

        if not videos:
            return
        videoNum = 0
        for url in videos:
            content = await self.xhs_client.get_note_media(url)
            if content is None:
                continue
            extension_file_name = f"{videoNum}.mp4"
            videoNum += 1
            await xhs_store.update_xhs_note_image(note_id, content, extension_file_name)
