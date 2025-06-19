import subprocess
import os
import json

def get_chrome_profiles():
    """获取所有 Chrome 用户配置"""
    # Chrome 用户数据目录
    user_data_dir = os.path.expanduser("~/Library/Application Support/Google/Chrome")
    local_state_path = os.path.join(user_data_dir, "Local State")

    profiles = {}

    if os.path.exists(local_state_path):
        try:
            with open(local_state_path, 'r', encoding='utf-8') as f:
                local_state = json.load(f)

            profile_info = local_state.get('profile', {}).get('info_cache', {})

            for profile_key, profile_data in profile_info.items():
                profile_name = profile_data.get('name', profile_key)
                profiles[profile_key] = profile_name

        except Exception as e:
            print(f"读取配置文件时出错: {e}")

    return profiles

def open_chrome_with_profile_selection():
    """列出所有配置并让用户选择"""
    profiles = get_chrome_profiles()
    print(profiles)

    if not profiles:
        print("未找到 Chrome 用户配置")
        return

    print("可用的 Chrome 用户配置:")
    profile_list = list(profiles.items())

    for i, (profile_key, profile_name) in enumerate(profile_list, 1):
        print(f"{i}. {profile_name} ({profile_key})")

    try:
        choice = int(input("请选择配置 (输入数字): ")) - 1
        if 0 <= choice < len(profile_list):
            selected_profile = profile_list[choice][0]
            print(selected_profile)

            chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            cmd = [chrome_path, f"--profile-directory={selected_profile}",f"--remote-debugging-port=9123"]

            subprocess.Popen(cmd)
            print(f"已打开 Chrome，使用配置: {profile_list[choice][1]}")
        else:
            print("无效选择")
    except ValueError:
        print("请输入有效数字")

if __name__ == "__main__":
    # 使用示例
    open_chrome_with_profile_selection()