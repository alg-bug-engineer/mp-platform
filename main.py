import uvicorn
from core.config import cfg
from core.print import print_warning
import threading
from driver.auth import *
import os

# --- 代理抑制逻辑：禁止使用 127.0.0.1:7890 ---
def suppress_forbidden_proxies():
    forbidden = ["127.0.0.1:7890", "localhost:7890"]
    env_vars = ["http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]
    for env in env_vars:
        val = os.getenv(env)
        if val:
            for f in forbidden:
                if f in val:
                    print(f"警告: 检测到全局禁止使用的代理配置 {env}={val}，已从进程环境中清除。")
                    os.environ.pop(env, None)
                    break
    
    # 发布 CSDN、公众号是不需要代理的，强制在 NO_PROXY 中添加这些域名
    no_proxy_domains = "mp.weixin.qq.com,api.weixin.qq.com,csdn.net,editor.csdn.net,passport.csdn.net"
    current_no_proxy = os.getenv("no_proxy") or os.getenv("NO_PROXY") or ""
    if current_no_proxy:
        new_no_proxy = f"{current_no_proxy},{no_proxy_domains}"
    else:
        new_no_proxy = no_proxy_domains
    
    os.environ["no_proxy"] = new_no_proxy
    os.environ["NO_PROXY"] = new_no_proxy
    print(f"代理优化: 已在 NO_PROXY 中强制排除以下域名: {no_proxy_domains}")

suppress_forbidden_proxies()

if __name__ == '__main__':
    print("环境变量:")
    for k,v in os.environ.items():
        print(f"{k}={v}")
    if cfg.args.init=="True":
        import init_sys as init
        init.init()
    if  cfg.args.job =="True" and cfg.get("server.enable_job",False):
        from jobs import start_all_task
        threading.Thread(target=start_all_task,daemon=False).start()
    else:
        print_warning("未开启定时任务")
    print("启动服务器")
    AutoReload=cfg.get("server.auto_reload",False)
    thread=cfg.get("server.threads",1)
    uvicorn.run("web:app", host="0.0.0.0", port=int(cfg.get("port",8001)),
            reload=AutoReload,
            reload_dirs=['core','web_ui'],
            reload_excludes=['static','web_ui','data'], 
            workers=thread,
            log_config=None,
            )
    pass