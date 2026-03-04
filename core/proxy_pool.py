import threading
import time
import requests
import re
import random
from typing import List, Set
from core.log import get_logger

# 获取专用代理日志器
logger = get_logger("proxy")

class ProxyPool:
    """免费代理池管理器"""
    
    def __init__(self):
        self.proxies: Set[str] = set()
        self.lock = threading.Lock()
        self.running = False
        self.check_interval = 300  # 5分钟检查一次健康性
        self.fetch_interval = 1800 # 30分钟抓取一次新IP
        
        # 预置一些抓取源
        self.fetchers = [
            self._fetch_ip3366,
            self._fetch_kuaidaili,
            self._fetch_xsdaili,
            self._fetch_proxyscrape,
            self._fetch_openproxy
        ]

    def start(self):
        """启动后台维护线程"""
        if self.running:
            return
        self.running = True
        
        # 启动抓取线程
        threading.Thread(target=self._fetch_loop, daemon=True).start()
        # 启动检查线程
        threading.Thread(target=self._check_loop, daemon=True).start()
        logger.info("代理池后台维护线程已启动")

    def stop(self):
        """停止后台维护线程"""
        self.running = False

    def get_proxy(self) -> str:
        """获取一个随机的有效代理，排除禁止使用的 127.0.0.1:7890"""
        with self.lock:
            if not self.proxies:
                return ""
            
            # 过滤掉禁止使用的代理
            forbidden_ips = ["127.0.0.1:7890", "localhost:7890"]
            valid_proxies = [p for p in self.proxies if p not in forbidden_ips]
            
            if not valid_proxies:
                return ""
                
            return random.choice(valid_proxies)

    def remove_proxy(self, proxy: str):
        """移除失效代理"""
        with self.lock:
            if proxy in self.proxies:
                self.proxies.discard(proxy)
                logger.info(f"移除失效代理: {proxy}, 当前剩余: {len(self.proxies)}")

    def _fetch_loop(self):
        """循环抓取新代理"""
        while self.running:
            logger.info("开始抓取新代理...")
            new_ips = set()
            for fetcher in self.fetchers:
                try:
                    ips = fetcher()
                    new_ips.update(ips)
                    logger.debug(f"{fetcher.__name__} 抓取到 {len(ips)} 个IP")
                except Exception as e:
                    logger.error(f"{fetcher.__name__} 抓取失败: {e}")
            
            # 验证新抓取的IP
            valid_new_ips = self._validate_batch(list(new_ips))
            
            with self.lock:
                before_count = len(self.proxies)
                self.proxies.update(valid_new_ips)
                after_count = len(self.proxies)
                logger.info(f"抓取完成，新增有效代理 {len(valid_new_ips)} 个，当前总数: {after_count}")
            
            time.sleep(self.fetch_interval)

    def _check_loop(self):
        """循环检查现有代理健康性"""
        while self.running:
            if not self.proxies:
                time.sleep(60)
                continue
                
            logger.info("开始例行检查代理池健康性...")
            with self.lock:
                current_proxies = list(self.proxies)
            
            valid_ips = self._validate_batch(current_proxies)
            
            with self.lock:
                self.proxies = set(valid_ips)
                logger.info(f"健康性检查完成，剩余有效代理 {len(self.proxies)} 个")
            
            time.sleep(self.check_interval)

    def _validate_batch(self, ips: List[str]) -> List[str]:
        """批量验证IP有效性"""
        valid_ips = []
        threads = []
        
        def check(ip):
            if self._is_valid(ip):
                valid_ips.append(ip)

        for ip in ips:
            t = threading.Thread(target=check, args=(ip,))
            t.start()
            threads.append(t)
            
            # 限制并发验证线程数
            if len(threads) >= 20:
                for t in threads:
                    t.join()
                threads = []
        
        for t in threads:
            t.join()
            
        return valid_ips

    def _is_valid(self, proxy: str) -> bool:
        """验证单个代理是否有效"""
        test_url = "http://httpbin.org/ip"
        try:
            proxies = {"http": f"http://{proxy}", "https": f"http://{proxy}"}
            # 缩短超时时间到 3s，提高筛选效率
            resp = requests.get(test_url, proxies=proxies, timeout=3)
            if resp.status_code == 200:
                logger.debug(f"代理有效: {proxy}")
                return True
        except:
            pass
        logger.debug(f"代理失效: {proxy}")
        return False

    # --- 具体的抓取实现 ---

    def _fetch_proxyscrape(self) -> List[str]:
        """抓取 ProxyScrape (免费 API)"""
        ips = []
        url = "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                for line in resp.text.splitlines():
                    if ":" in line:
                        ips.append(line.strip())
        except Exception as e:
            logger.error(f"ProxyScrape 抓取异常: {e}")
        return ips

    def _fetch_openproxy(self) -> List[str]:
        """抓取 OpenProxy.space (免费 API)"""
        ips = []
        url = "https://api.openproxy.space/lists/http"
        try:
            # 这里的接口可能返回JSON或文本，根据常见公开API适配
            resp = requests.get(url, timeout=10)
            matches = re.findall(r'(\d+\.\d+\.\d+\.\d+):(\d+)', resp.text)
            for ip, port in matches:
                ips.append(f"{ip}:{port}")
        except:
            pass
        return ips

    def _fetch_ip3366(self) -> List[str]:
        """抓取云代理 (ip3366.net)"""
        ips = []
        urls = [
            "http://www.ip3366.net/free/?stype=1",
            "http://www.ip3366.net/free/?stype=2"
        ]
        headers = {"User-Agent": "Mozilla/5.0"}
        for url in urls:
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                matches = re.findall(r'<td>(\d+\.\d+\.\d+\.\d+)</td>\s*<td>(\d+)</td>', resp.text)
                for ip, port in matches:
                    ips.append(f"{ip}:{port}")
            except:
                continue
        return ips

    def _fetch_kuaidaili(self) -> List[str]:
        """抓取快代理 (kuaidaili.com)"""
        ips = []
        urls = [
            "https://www.kuaidaili.com/free/inha/",
            "https://www.kuaidaili.com/free/intr/"
        ]
        headers = {"User-Agent": "Mozilla/5.0"}
        for url in urls:
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                matches = re.findall(r'<td data-title="IP">(\d+\.\d+\.\d+\.\d+)</td>\s*<td data-title="PORT">(\d+)</td>', resp.text)
                for ip, port in matches:
                    ips.append(f"{ip}:{port}")
                time.sleep(1) # 快代理有频率限制
            except:
                continue
        return ips

    def _fetch_xsdaili(self) -> List[str]:
        """抓取小舒代理 (xsdaili.cn)"""
        ips = []
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            # 先获取最新页面的URL
            main_url = "http://www.xsdaili.cn/"
            resp = requests.get(main_url, headers=headers, timeout=10)
            matches = re.findall(r'<a href="(/dayproxy/ip/\d+\.html)">', resp.text)
            if matches:
                latest_url = main_url + matches[0].lstrip('/')
                resp = requests.get(latest_url, headers=headers, timeout=10)
                # 匹配 IP:PORT@TYPE#LOCATION
                matches = re.findall(r'(\d+\.\d+\.\d+\.\d+):(\d+)', resp.text)
                for ip, port in matches:
                    ips.append(f"{ip}:{port}")
        except:
            pass
        return ips

# 全局单例
proxy_pool = ProxyPool()
