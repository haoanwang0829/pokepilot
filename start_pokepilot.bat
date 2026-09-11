@echo off
chcp 65001 >nul
title PokePilot UI 服务
echo.
echo ==============================================
echo           PokePilot 正在启动...
echo ==============================================
echo.

:: 关键：脚本在当前目录运行，自动识别路径，无需手动修改！
cd /d "%~dp0"

:: 启动命令
python -m pokepilot.ui.ui_server

echo.
echo 服务已关闭，按任意键退出...
pause >nul