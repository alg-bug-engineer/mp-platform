import os
import platform
import subprocess
import sys
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from webdriver_manager.firefox import GeckoDriverManager
from selenium.common.exceptions import WebDriverException

class FirefoxController:
    def __init__(self):
        self.system = platform.system().lower()
        self.driver_path = None
        self.browser_path = None
        self.options = Options()
        
        # 设置跨平台兼容的默认选项
        self.options.set_preference("dom.webnotifications.enabled", False)
        self.options.set_preference("dom.push.enabled", False)
        
    def _download_file(self, url, save_path):
        """下载文件并显示进度"""
        import requests
        from tqdm import tqdm
        
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        block_size = 1024
        
        with open(save_path, 'wb') as f:
            with tqdm(total=total_size, unit='B', unit_scale=True, desc=save_path) as pbar:
                for data in response.iter_content(block_size):
                    f.write(data)
                    pbar.update(len(data))
    
    def _get_latest_firefox_url(self):
        """获取最新版Firefox下载链接"""
        return "https://cdn.stubdownloader.services.mozilla.com/builds/firefox-beta-latest-ssl/zh-CN/win64/2bcaf1071892df9bcf7a233fbc4800c1044ce1f73f4d94d07b2fbdad3735d313/Firefox%20Setup%20139.0b10.exe"
    def _install_firefox_windows(self):
        """Windows平台安装Firefox"""
        import tempfile
        import os
        
        print("正在下载Firefox安装包...")
        download_url = self._get_latest_firefox_url()
        temp_dir = tempfile.gettempdir()
        installer_path = os.path.join(temp_dir, "firefox_installer.exe")
        
        try:
            self._download_file(download_url, installer_path)
            print("正在安装Firefox...")
            subprocess.run([installer_path, "/S"], check=True)
            print("Firefox安装完成")
        finally:
            if os.path.exists(installer_path):
                os.remove(installer_path)
    
    def _install_firefox(self):
        """自动安装Firefox浏览器"""
        try:
            if self.system == "windows":
                # Windows安装逻辑
                if not self._is_firefox_installed_windows():
                    self._install_firefox_windows()
            elif self.system == "linux":
                # Linux安装逻辑
                if not self._is_firefox_installed_linux():
                    print("正在通过包管理器安装Firefox...")
                    subprocess.run(["sudo", "apt-get", "install", "-y", "firefox"], check=True)
        except Exception as e:
            print(f"Firefox安装失败: {str(e)}")
            raise

    def _is_firefox_installed_windows(self):
        """检查Windows是否已安装Firefox"""
        common_paths = [
            os.path.expandvars("%PROGRAMFILES%\\Mozilla Firefox\\firefox.exe"),
            os.path.expandvars("%PROGRAMFILES(x86)%\\Mozilla Firefox\\firefox.exe")
        ]
        return any(os.path.exists(path) for path in common_paths)

    def _is_firefox_installed_linux(self):
        """检查Linux是否已安装Firefox"""
        try:
            subprocess.run(["which", "firefox"], check=True, stdout=subprocess.PIPE)
            return True
        except subprocess.CalledProcessError:
            return False

    def _validate_existing_driver(self, path):
        """验证现有驱动是否可用"""
        if not os.path.exists(path):
            return False
        if self.system == "linux":
            if not os.access(path, os.X_OK):
                try:
                    os.chmod(path, 0o755)
                except:
                    return False
        return True

    def _setup_driver(self):
        """自动配置geckodriver"""
        # 优先检查本地驱动
        local_driver = os.path.join(os.path.dirname(__file__), "driver", "geckodriver")
        if self._validate_existing_driver(local_driver):
            self.driver_path = local_driver
            print("使用本地驱动:", local_driver)
            return
            
        # 本地驱动不可用则尝试自动下载
        try:
            # 使用国内镜像源配置
            os.environ['WDM_SSL_VERIFY'] = '0'
            os.environ['WDM_LOCAL'] = '1'
            
            # 尝试使用清华镜像源
            try:
                self.driver_path = GeckoDriverManager(
                    url="https://mirrors.tuna.tsinghua.edu.cn/github-release/mozilla/geckodriver/",
                    latest_release_url="https://mirrors.tuna.tsinghua.edu.cn/github-release/mozilla/geckodriver/LatestRelease/",
                    cache_valid_range=365
                ).install()
            except Exception as mirror_error:
                print("镜像源下载失败，尝试官方源...")
                try:
                    self.driver_path = GeckoDriverManager().install()
                except Exception as official_error:
                    print("驱动自动安装失败，请手动下载:")
                    print("1. 访问 https://github.com/mozilla/geckodriver/releases")
                    print("2. 下载对应系统的版本")
                    print("3. 解压后将geckodriver放入driver/driver目录")
                    raise official_error
            
            # 设置浏览器路径
            if self.system == "windows":
                self.browser_path = next(
                    (p for p in [
                        os.path.expandvars("%PROGRAMFILES%\\Mozilla Firefox\\firefox.exe"),
                        os.path.expandvars("%PROGRAMFILES(x86)%\\Mozilla Firefox\\firefox.exe")
                    ] if os.path.exists(p)), None)
            elif self.system == "linux":
                self.browser_path = "/usr/bin/firefox"
            
            if not self.browser_path:
                raise Exception("无法找到Firefox浏览器路径")
                
            self.options.binary_location = self.browser_path
        except Exception as e:
            print(f"驱动配置失败: {str(e)}")
            raise

    def start_browser(self, headless=False):
        """启动浏览器"""
        try:
            self._install_firefox()
            self._setup_driver()
            
            if headless:
                self.options.add_argument("--headless")
            
            service = Service(executable_path=self.driver_path)
            self.driver = webdriver.Firefox(service=service, options=self.options)
            return self.driver
        except WebDriverException as e:
            print(f"浏览器启动失败: {str(e)}")
            raise

    def open_url(self, url):
        """打开指定URL"""
        if not hasattr(self, 'driver'):
            raise Exception("浏览器未启动，请先调用start_browser()")
        self.driver.get(url)

    def close(self):
        """关闭浏览器"""
        if hasattr(self, 'driver'):
            self.driver.quit()

# 示例用法
# if __name__ == "__main__":
#     controller = FirefoxController()
#     try:
#         controller.start_browser()
#         controller.open_url("https://mp.weixin.qq.com/")
#     finally:
#         controller.close()