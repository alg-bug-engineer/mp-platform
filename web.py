from fastapi import FastAPI, Request, APIRouter, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.openapi.models import OAuthFlows as OAuthFlowsModel
from fastapi.openapi.models import OAuthFlowPassword
from fastapi.openapi.utils import get_openapi
import json
from typing import Any
from apis.auth import router as auth_router
from apis.user import router as user_router
from apis.article import router as article_router
from apis.mps import router as wx_router
from apis.res import router as res_router
from apis.rss import router as rss_router,feed_router
from apis.config_management import router as config_router
from apis.message_task import router as task_router
from apis.sys_info import router as sys_info_router
from apis.tags import router as tags_router
from apis.export import router as export_router
from apis.tools import router as tools_router
from apis.ai import router as ai_router
from apis.github_update import router as github_router
from apis.billing import router as billing_router
from apis.analytics import router as analytics_router
from views import router as views_router
import apis
import os
import time
from core.config import cfg,VERSION,API_BASE
from core.db import DB
from core.analytics_service import (
    analytics_enabled,
    build_api_event,
    parse_bearer_user,
    save_event,
)


class UnicodeJSONResponse(JSONResponse):
    """自定义 JSON 响应类，确保中文不被转义"""
    def render(self, content: Any) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,  # 关键：不转义非ASCII字符
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")


app = FastAPI(
    title="WeRSS API",
    description="微信公众号RSS生成服务API文档",
    version="1.0.0",
    docs_url="/api/docs",  # 指定文档路径
    redoc_url="/api/redoc",  # 指定Redoc路径
    # 指定OpenAPI schema路径
    openapi_url="/api/openapi.json",
    openapi_tags=[
        {
            "name": "认证",
            "description": "用户认证相关接口",
        }
    ],
    swagger_ui_parameters={
        "persistAuthorization": True,
        "withCredentials": True,
    },
    # 使用自定义 JSONResponse 确保中文不被转义为 \uXXXX
    default_response_class=UnicodeJSONResponse,
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.middleware("http")
async def add_custom_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Version"] = VERSION
    response.headers["X-Powered-By"] = "Content Platform"
    response.headers["Server"] = cfg.get("app_name", "WeRSS")
    return response


@app.middleware("http")
async def add_analytics_event(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)

    try:
        if not analytics_enabled():
            return response
        path = str(request.url.path or "")
        if path.startswith(("/assets", "/static", "/files")):
            return response
        if path in ("/favicon.ico", "/api/openapi.json", "/api/docs", "/api/redoc"):
            return response
        if path.startswith(f"{API_BASE}/analytics"):
            return response

        duration_ms = int((time.perf_counter() - start) * 1000)
        auth_user = parse_bearer_user(request.headers.get("Authorization", ""))
        session = DB.get_session()
        try:
            if path.startswith("/api/"):
                payload = build_api_event(
                    path=path,
                    method=request.method,
                    status_code=int(response.status_code or 0),
                    duration_ms=duration_ms,
                    user_info=auth_user,
                    session_id=str(request.headers.get("X-Session-Id", "") or ""),
                )
            else:
                payload = {
                    "event_type": "page_request",
                    "page": path,
                    "path": path,
                    "method": request.method,
                    "status_code": int(response.status_code or 0),
                    "duration_ms": duration_ms,
                    "username": auth_user.get("username", ""),
                    "owner_id": auth_user.get("username", ""),
                    "session_id": str(request.headers.get("X-Session-Id", "") or ""),
                }
            save_event(session, payload)
            session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()
    except Exception:
        pass

    return response
# 创建API路由分组
api_router = APIRouter(prefix=f"{API_BASE}")
api_router.include_router(auth_router)
api_router.include_router(user_router)
api_router.include_router(article_router)
api_router.include_router(wx_router)
api_router.include_router(config_router)
api_router.include_router(task_router)
api_router.include_router(sys_info_router)
api_router.include_router(tags_router)
api_router.include_router(export_router)
api_router.include_router(tools_router)
api_router.include_router(ai_router)
api_router.include_router(github_router)
api_router.include_router(billing_router)
api_router.include_router(analytics_router)

resource_router = APIRouter(prefix="/static")
resource_router.include_router(res_router)
feeds_router = APIRouter()
feeds_router.include_router(rss_router)
feeds_router.include_router(feed_router)
# 注册API路由分组
app.include_router(api_router)
app.include_router(resource_router)
app.include_router(feeds_router)
app.include_router(views_router)


@app.on_event("startup")
async def ensure_tables():
    try:
        DB.create_tables()
    except Exception:
        pass

# 静态文件服务配置
app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")
app.mount("/static", StaticFiles(directory="static"), name="static")
from core.res.avatar import files_dir
app.mount("/files", StaticFiles(directory=files_dir), name="files")
# app.mount("/docs", StaticFiles(directory="./data/docs"), name="docs")
@app.get("/{path:path}",tags=['默认'],include_in_schema=False)
async def serve_vue_app(request: Request, path: str):
    """处理Vue应用路由"""
    # 排除API和静态文件路由
    if path.startswith(('api', 'assets', 'static')) or path in ['favicon.ico','vite.svg','logo.svg']:
        return None
    
    # 返回Vue入口文件
    index_path = os.path.join("static", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    
    return {"error": "Not Found"}, 404

@app.get("/",tags=['默认'],include_in_schema=False)
async def serve_root(request: Request):
    """处理根路由"""
    return await serve_vue_app(request, "")
