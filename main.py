import asyncio
import os
import io
import random
from datetime import datetime
import time
import platform
import logging
from tabulate import tabulate
from configparser import ConfigParser
from pydoll.browser.chromium import Chrome
from pydoll.browser.options import ChromiumOptions


from pydoll.commands import InputCommands
# from pydoll.connection import ConnectionHandler
# from pydoll.commands.InputCommands import dispatch_mouse_event, dispatch_key_event
from pydoll.connection.connection_handler import ConnectionHandler


from pydoll.constants import MouseEventType, MouseButton

# 自动判断运行环境
IS_GITHUB_ACTIONS = 'GITHUB_ACTIONS' in os.environ
IS_SERVER = platform.system() == "Linux" and not IS_GITHUB_ACTIONS


# 创建一个 StringIO 对象用于捕获日志
log_stream = io.StringIO()

# 创建日志记录器
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 创建控制台输出的处理器
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# 创建 log_stream 处理器
stream_handler = logging.StreamHandler(log_stream)
stream_handler.setLevel(logging.INFO)

# 创建格式化器
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# 为处理器设置格式化器
console_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)

# 将处理器添加到日志记录器中
logger.addHandler(console_handler)
logger.addHandler(stream_handler)


# 从配置文件或环境变量中读取配置信息
def load_config():
    config = ConfigParser()
    if IS_SERVER:
        config_file = './config/config.ini'
    elif IS_GITHUB_ACTIONS:
        config_file = None
    else:
        config_file = 'config/config.ini'

    if config_file and os.path.exists(config_file):
        config.read(config_file)

    return config


async def login(tab, USERNAME, PASSWORD) -> bool:
    logging.info("尝试登录...")
    # star_button = await tab.find(
    #     # tag_name='button',
    #     class_name="login-button d-button-label",
    #     timeout=5,
    #     raise_exc=False
    # )
    # star_button.click()
    # await asyncio.sleep(3)

    await tab.go_to("https://linux.do/login")
    await asyncio.sleep(3)
    name_input = await tab.find(
        id="login-account-name",
    )
    await name_input.type_text(USERNAME, interval=0.15)
    await asyncio.sleep(3)
    pwd_input = await tab.find(
        id="login-account-password",
    )
    await pwd_input.click()
    await pwd_input.type_text(PASSWORD, interval=0.15)
    await asyncio.sleep(3)
    login_btn = await tab.find(id="login-button")
    await login_btn.click()
    await asyncio.sleep(10)  # 等待页面加载完成
    user_ele = await tab.find(id="current-user")
    if not user_ele:
        logging.error("登录失败，请检查账号密码及是否关闭二次认证")
        return False
    else:
        logging.info("登录成功")
        return True


async def visit_article_and_scroll(tab,goDone):
    try:
        # 随机滚动页面5到10秒
        scroll_duration = random.randint(5, 10)
        logging.info(f"随机滚动页面 {scroll_duration} 秒...")
        scroll_end_time = time.time() + scroll_duration

        # 创建连接处理器
        # connection = ConnectionHandler()

        while time.time() < scroll_end_time:
            scroll_distance = random.randint(300, 600)  # 每次滚动的距离，随机选择
            # page.mouse.wheel(0, scroll_distance)
            scroll_command = InputCommands.dispatch_mouse_event(MouseEventType.MOUSE_WHEEL ,200, 200,delta_y=-scroll_distance,button=MouseButton.MIDDLE)
            # await connection.execute_command(scroll_command)
            js = """window.scrollBy({
              top: 800,   // 垂直滚动距离（向下滚动为正值）
              left: 0,    // 水平滚动距离（为0表示水平不滚动）
              behavior: 'smooth' // 滚动行为：smooth 表示平滑滚动
            });"""
                  # .format(scroll_distance))
            js_done = """function scrollToBottomSmooth() {
              const scrollStep = 50; // 每次滚动的距离
              const scrollTop = window.scrollY; // 当前滚动位置
              const windowHeight = window.innerHeight; // 当前窗口高度
              const scrollHeight = document.documentElement.scrollHeight; // 页面整体高度
            
              if (scrollTop + windowHeight < scrollHeight) {
                // 向下滚动
                window.scrollBy(0, scrollStep);
                // 再次执行下一步滚动
                requestAnimationFrame(scrollToBottomSmooth);
              }
            }
            
            // 调用函数
            scrollToBottomSmooth();"""
            if goDone:
                await tab.execute_script(js_done)
            else:
                await tab.execute_script(js)
            # await tab.execute_command(scroll_command)
            await asyncio.sleep(random.uniform(0.5, 1.5))  # 随机等待0.5到1.5秒再滚动

        logging.info("页面滚动完成")

    except Exception as e:
        logging.error(f"滚动页面时出错: {e}")

async def click_like(tab):
        try:
            # page.wait_for_selector(".discourse-reactions-reaction-button button", timeout=2000)
            like_button =  await tab.find(class_name="discourse-reactions-reaction-button button", timeout=2000)
            if like_button:
                await like_button.click()
                logging.info("文章已点赞")
            else:
                logging.info("未找到点赞按钮")
        except TimeoutError:
            logging.warning("点赞按钮定位超时")
        except Exception as e:
            logging.error(f"点赞操作失败: {e}")


async def click_topic(browser,tab,HOME_URL,MAX_TOPICS,LIKE_PROBABILITY):
    try:
        logging.info("开始处理主题...")
        # 随机滚动页面
        await visit_article_and_scroll(tab,False)
        logging.info(await browser.get_version())
        # 加载主题
        topics = await tab.query("//*[@id=\"list-area\"]//table[@class='topic-list']//tr/td//a[@title and not(ancestor::span[contains(@class, 'topic-statuses')]/a[contains(@class, 'pinned')])]", find_all=True)
        logging.info(topics)
        total_topics = len(topics)
        logging.info(f"共找到 {total_topics} 个主题。")

        # 限制处理的最大主题数
        if total_topics > MAX_TOPICS:
            logging.info(f"处理主题数超过最大限制 {MAX_TOPICS}，仅处理前 {MAX_TOPICS} 个主题。")
            topics = topics[:MAX_TOPICS]

        skip_articles = []
        skip_count = 0
        browsed_articles = []
        browsed_count = 0
        liked_articles = []
        like_count = 0
        replied_articles = []
        reply_count = 0
        collected_articles = []
        collect_count = 0

        for idx, topic in enumerate(topics):

            article_title = await topic.text

            article_url = HOME_URL + topic.get_attribute("href")

            logging.info(f"打开第 {idx + 1}/{len(topics)} 个主题 ：{article_title.strip()} ... ")

            # 访问文章页面
            article_tab = await browser.new_tab(article_url)

            try:

                # 访问文章数累加
                browsed_count += 1
                # 访问文章数信息记录
                browsed_articles.append({"title": article_title, "url": article_url})
                # 等待页面完全加载
                time.sleep(3)
                # 随机滚动页面
                await visit_article_and_scroll(article_tab,True)
                if random.random() < LIKE_PROBABILITY:
                    await click_like(article_tab)
                    liked_articles.append({"title": article_title, "url": article_url})
                    like_count += 1
                # if random.random() < REPLY_PROBABILITY:
                #     reply_message = self.click_reply(page)
                #     if reply_message:
                #         replied_articles.append(
                #             {"title": article_title, "url": article_url, "reply": reply_message})
                #         reply_count += 1
                # if random.random() < COLLECT_PROBABILITY:
                #     self.click_collect(page)
                #     collected_articles.append({"title": article_title, "url": article_url})
                #     collect_count += 1

            except TimeoutError:
                logging.warning(f"打开主题 ： {article_title} 超时，跳过该主题。")
            finally:
                time.sleep(3)  # 等待一段时间，防止操作过快导致出错
                await article_tab.close()
                logging.info(f"已关闭第 {idx + 1}/{len(topics)} 个主题 ： {article_title} ...")

        # 打印跳过的文章信息
        logging.info(f"一共跳过了 {skip_count} 篇文章。")
        if skip_count > 0:
            logging.info("--------------跳过的文章信息-----------------")
            logging.info("\n%s",tabulate(skip_articles, headers="keys", tablefmt="pretty"))

        # 打印浏览的文章信息
        logging.info(f"一共浏览了 {browsed_count} 篇文章。")
        if browsed_count > 0:
            logging.info("--------------浏览的文章信息-----------------")
            logging.info("\n%s",tabulate(browsed_articles, headers="keys", tablefmt="pretty"))

        # 打印点赞的文章信息
        logging.info(f"一共点赞了 {like_count} 篇文章。")
        if like_count > 0:
            logging.info("--------------点赞的文章信息-----------------")
            logging.info("\n%s",tabulate(liked_articles, headers="keys", tablefmt="pretty"))

        # 打印回复的文章信息
        logging.info(f"一共回复了 {reply_count} 篇文章。")
        if reply_count > 0:
            logging.info("--------------回复的文章信息-----------------")
            logging.info("\n%s",tabulate(replied_articles, headers="keys", tablefmt="pretty"))

        # 打印加入书签的文章信息
        logging.info(f"一共加入书签了 {collect_count} 篇文章。")
        if collect_count > 0:
            logging.info("--------------加入书签的文章信息-----------------")
            logging.info("\n%s", tabulate(collected_articles, headers="keys", tablefmt="pretty"))

    except Exception as e:
        logging.info(f"处理主题时出错: {e}")



async def main():
    config = load_config()

    USERNAME = os.getenv("LINUXDO_USERNAME", config.get('credentials', 'username', fallback=None))
    PASSWORD = os.getenv("LINUXDO_PASSWORD", config.get('credentials', 'password', fallback=None))
    LIKE_PROBABILITY = float(os.getenv("LIKE_PROBABILITY", config.get('settings', 'like_probability', fallback='0.02')))
    REPLY_PROBABILITY = float(os.getenv("REPLY_PROBABILITY", config.get('settings', 'reply_probability', fallback='0')))
    COLLECT_PROBABILITY = float(
        os.getenv("COLLECT_PROBABILITY", config.get('settings', 'collect_probability', fallback='0.02')))
    HOME_URL = config.get('urls', 'home_url', fallback="https://linux.do/")
    CONNECT_URL = config.get('urls', 'connect_url', fallback="https://connect.linux.do/")
    USE_WXPUSHER = os.getenv("USE_WXPUSHER", config.get('wxpusher', 'use_wxpusher', fallback='false')).lower() == 'true'
    APP_TOKEN = os.getenv("APP_TOKEN", config.get('wxpusher', 'app_token', fallback=None))
    TOPIC_ID = os.getenv("TOPIC_ID", config.get('wxpusher', 'topic_id', fallback=None))
    MAX_TOPICS = int(os.getenv("MAX_TOPICS", config.get('settings', 'max_topics', fallback='50')))

    # 检查必要配置
    missing_configs = []

    if not USERNAME:
        missing_configs.append("USERNAME")
    if not PASSWORD:
        missing_configs.append("PASSWORD")
    if USE_WXPUSHER and not APP_TOKEN:
        missing_configs.append("APP_TOKEN")
    if USE_WXPUSHER and not TOPIC_ID:
        missing_configs.append("TOPIC_ID")

    if missing_configs:
        logging.error(f"缺少必要配置: {', '.join(missing_configs)}，请在环境变量或配置文件中设置。")
        exit(1)

    options = ChromiumOptions()
    # options.binary_location = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    options.add_argument('--headless=new')
    options.add_argument('--start-maximized')
    options.add_argument("--no-sandbox")
    options.add_argument('--disable-notifications')

    async with Chrome(options=options) as browser:
        tab = await browser.start()

        # await tab.go_to(HOME_URL)

        # await asyncio.sleep(3)

        re = login(tab, USERNAME, PASSWORD)
        await re

        await tab.go_to("https://linux.do/unseen?ascending=false&order=posts")

        await click_topic(browser,tab,HOME_URL,MAX_TOPICS,LIKE_PROBABILITY)

        screenshot_path = os.path.join(os.getcwd(), 'pydoll_repo.png')
        await tab.take_screenshot(path=screenshot_path)
        logging.info(f"Screenshot saved to: {screenshot_path}")

        base64_screenshot = await tab.take_screenshot(as_base64=True)


async def test():
    options = ChromiumOptions()
    options.binary_location = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    # options.add_argument('--headless=new')
    options.add_argument('--start-maximized')
    options.add_argument('--disable-notifications')

    async with (Chrome(options=options) as browser):
        tab = await browser.start()
        await tab.go_to("https://linux.do")
        await visit_article_and_scroll(tab,False)
        topics = await tab.query("//*[@id=\"list-area\"]//table[@class='topic-list']//tr/td//a[@class=\"title raw-link raw-topic-link\"]", find_all=True)
        logging.info(topics)
        total_topics = len(topics)
        logging.info(f"共找到 {total_topics} 个主题。")
        for idx, topic in enumerate(topics):
            article_title = await topic.text
            logging.info(f"{idx}. {article_title.strip()}")

if __name__ == "__main__":
    start_time = datetime.now()
    logging.info(f"开始执行时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    try:
        # asyncio.run(test())
        asyncio.run(main())
    except Exception as e:
        logging.error(f"运行过程中出错: {e}")
    finally:
        end_time = datetime.now()
        logging.info(f"结束执行时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
