import asyncio
import os
import platform
import logging
from pydoll.browser.chromium import Chrome
from pydoll.browser.options import ChromiumOptions
from configparser import ConfigParser


# 自动判断运行环境
IS_GITHUB_ACTIONS = 'GITHUB_ACTIONS' in os.environ
IS_SERVER = platform.system() == "Linux" and not IS_GITHUB_ACTIONS

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


async def login(tab,USERNAME,PASSWORD) -> bool:

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
        print("sleep")
        name_input =await tab.find(
            id="login-account-name",
        )
        print(name_input)
        await name_input.insert_text(USERNAME)
        await asyncio.sleep(3)
        pwd_input =await tab.find(
            id="login-account-password",
        )
        await pwd_input.insert_text(PASSWORD)
        await asyncio.sleep(3)
        login_btn = await tab.find(id="login-button")
        await login_btn.click()
        await asyncio.sleep(10)  # 等待页面加载完成
        user_ele = tab.query_selector("#current-user")
        if not user_ele:
            logging.error("登录失败，请检查账号密码及是否关闭二次认证")
            return False
        else:
            logging.info("登录成功")
            return True


async def bu(tab):
    star_button = await tab.find(
        tag_name='button',
        timeout=5,
        raise_exc=False
    )
    if not star_button:
        print("Ops! The button was not found.")
        return

    await star_button.click()

async def main():
    config = load_config()


    USERNAME = os.getenv("LINUXDO_USERNAME", config.get('credentials', 'username', fallback=None))
    PASSWORD = os.getenv("LINUXDO_PASSWORD", config.get('credentials', 'password', fallback=None))
    LIKE_PROBABILITY = float(os.getenv("LIKE_PROBABILITY", config.get('settings', 'like_probability', fallback='0.02')))
    REPLY_PROBABILITY = float(os.getenv("REPLY_PROBABILITY", config.get('settings', 'reply_probability', fallback='0')))
    COLLECT_PROBABILITY = float(os.getenv("COLLECT_PROBABILITY", config.get('settings', 'collect_probability', fallback='0.02')))
    HOME_URL = config.get('urls', 'home_url', fallback="https://linux.do/")
    CONNECT_URL = config.get('urls', 'connect_url', fallback="https://connect.linux.do/")
    USE_WXPUSHER = os.getenv("USE_WXPUSHER", config.get('wxpusher', 'use_wxpusher', fallback='false')).lower() == 'true'
    APP_TOKEN = os.getenv("APP_TOKEN", config.get('wxpusher', 'app_token', fallback=None))
    TOPIC_ID = os.getenv("TOPIC_ID", config.get('wxpusher', 'topic_id', fallback=None))
    MAX_TOPICS = int(os.getenv("MAX_TOPICS", config.get('settings', 'max_topics', fallback='10')))

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
    options.binary_location = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    # options.add_argument('--headless=new')
    options.add_argument('--start-maximized')
    options.add_argument('--disable-notifications')

    async with Chrome(options=options) as browser:
        tab = await browser.start()
        # await tab.go_to(HOME_URL)

        # await asyncio.sleep(3)

        re = login(tab,USERNAME,PASSWORD)
        await re

        screenshot_path = os.path.join(os.getcwd(), 'pydoll_repo.png')
        await tab.take_screenshot(path=screenshot_path)
        print(f"Screenshot saved to: {screenshot_path}")

        base64_screenshot = await tab.take_screenshot(as_base64=True)

        repo_description_element = await tab.find(
            class_name='f4.my-3'
        )
        repo_description = await repo_description_element.text
        print(f"Repository description: {repo_description}")

if __name__ == "__main__":
    asyncio.run(main())