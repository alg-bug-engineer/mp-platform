@echo off
chcp 65001
REM 读取Python配置文件中的版本号
for /f "tokens=1 delims==" %%v in ('python -c "from core.config import VERSION; print('VERSION=', VERSION)"') do set VERSION=%%v
set tag="v%VERSION%"
echo 当前版本: %VERSION% TAG: %tag%
pause
git add .
git tag  "v%VERSION%" -m "%1"
git commit -m %VERSION%
git push -u origin main 
git push origin  %tag%