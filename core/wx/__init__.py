from .model import *
from .base import WxGather
ga=WxGather()
def search_Biz(kw:str="",limit=5,offset=0,token:str="",cookie:str="",user_agent:str=""):
    return ga.search_Biz(kw,limit,offset,token=token,cookie=cookie,user_agent=user_agent)

if __name__ == '__main__':
    pass

