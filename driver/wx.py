import sys
from driver import FirefoxController
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from PIL import Image
from selenium.webdriver.common.action_chains import ActionChains
import time
import os
import re
import json

def check_dependencies():
    """检查必要的依赖包"""
    try:
        import selenium
        import PIL
    except ImportError as e:
        print("缺少必要的依赖包，请先安装：")
        print("pip install selenium Pillow")
        return False
    return True

def extract_token_from_requests(driver):
    """从页面中提取token"""
    try:
        # 尝试从当前URL获取token
        current_url = driver.current_url
        token_match = re.search(r'token=([^&]+)', current_url)
        if token_match:
            return token_match.group(1)
        
        # 尝试从localStorage获取
        token = driver.execute_script("return localStorage.getItem('token');")
        if token:
            return token
            
        # 尝试从sessionStorage获取
        token = driver.execute_script("return sessionStorage.getItem('token');")
        if token:
            return token
            
        # 尝试从cookie获取
        cookies = driver.get_cookies()
        for cookie in cookies:
            if 'token' in cookie['name'].lower():
                return cookie['value']
                
        return None
    except Exception as e:
        print(f"提取token时出错: {str(e)}")
        return None

def wxLogin():
    """
    微信公众平台登录流程：
    1. 检查依赖和环境
    2. 打开微信公众平台
    3. 全屏截图保存二维码
    4. 等待用户扫码登录
    5. 获取登录后的cookie和token
    """
    # 检查依赖
    if not check_dependencies():
        return None

    try:
        # 初始化浏览器控制器
        controller = FirefoxController()
        
        # 启动浏览器并打开微信公众平台
        print("正在启动浏览器...")
        controller.start_browser()
        controller.open_url("https://mp.weixin.qq.com/")
        
        # 等待页面完全加载
        print("正在加载登录页面...")
        time.sleep(2)
        
        # 滚动到二维码区域
        qrcode = controller.driver.find_element(By.CLASS_NAME, "login__type__container__scan__qrcode")
        ActionChains(controller.driver).move_to_element(qrcode).perform()
        
        # 确保二维码可见
        wait = WebDriverWait(controller.driver, 10)
        wait.until(EC.visibility_of(qrcode))
        
        # 全屏截图并裁剪二维码区域
        print("正在生成二维码图片...")
        controller.driver.save_screenshot("temp_screenshot.png")
        img = Image.open("temp_screenshot.png")
        
        # 获取二维码位置和尺寸
        location = qrcode.location
        size = qrcode.size
        left = location['x']
        top = location['y']
        right = location['x'] + size['width']
        bottom = location['y'] + size['height']
        
        # 裁剪并保存二维码
        img = img.crop((left, top, right, bottom))
        img.save("wx_qrcode.png")
        os.remove("temp_screenshot.png")
        
        print("二维码已保存为 wx_qrcode.png，请扫码登录...")
        
        # 等待登录成功（检测页面跳转）
        print("等待扫码登录...")
        wait.until(EC.url_contains("https://mp.weixin.qq.com/cgi-bin/home"))
        print("登录成功！")
        
        # 获取token
        token = extract_token_from_requests(controller.driver)
        
        # 获取cookie
        cookies = controller.driver.get_cookies()
        print("\n获取到的Cookie:")
        for cookie in cookies:
            print(f"{cookie['name']}={cookie['value']}")
            
        if token:
            print(f"\n获取到的Token: {token}")
        
        return {
            'cookies': cookies,
            'token': token
        }
        
    except Exception as e:
        print(f"\n错误发生: {str(e)}")
        print("可能的原因:")
        print("1. 请确保已安装Firefox浏览器")
        print("2. 请确保geckodriver已下载并配置到PATH中")
        print("3. 检查网络连接是否可以访问微信公众平台")
        return None
    finally:
        if 'controller' in locals():
            controller.close()

if __name__ == "__main__":
    print("微信公众平台登录脚本 v1.3")
    print("="*40)
    result = wxLogin()
    if result:
        print("\n登录结果:")
        print(f"Cookies数量: {len(result['cookies'])}")
        print(f"Token: {result['token']}")
    else:
        print("\n登录失败，请检查上述错误信息")
    print("="*40)