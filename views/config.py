import os
from core.config import cfg
class Config:
    base_path= "./public"
    #模板路径 
    public_dir = f"{base_path}/templates/"
    home_template = f"{base_path}/templates/home.html"
    mps_template = f"{base_path}/templates/mps.html"
    tags_template = f"{base_path}/templates/tags.html"
    tag_detail_template = f"{base_path}/templates/tag_detail.html"
    article_template = f"{base_path}/templates/article.html"
    article_detail_template = f"{base_path}/templates/article_detail.html"
    articles_template = f"{base_path}/templates/articles.html"
    site={
        "name": cfg.get("site.name", "Content Studio"),
        "description": cfg.get("site.description", "A commercial WeChat content studio"), 
        "keywords": cfg.get("site.keywords", "Content Studio,RSS,微信公众号,内容创作,内容分发"),
        "logo": cfg.get("site.logo", "/static/logo.svg"),
        "favicon": cfg.get("site.favicon", "/static/logo.svg"),
        "author": cfg.get("site.author", "Content Studio Team"),
        "copyright": cfg.get("site.copyright", "© 2026 Content Studio Team"),
    }
base = Config()
