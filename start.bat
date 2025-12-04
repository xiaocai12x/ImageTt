@echo off
chcp 65001 >nul
title ImageTt 启动

echo ==========================================
echo      正在检查并安装依赖库，请稍候...
echo      (第一次运行需要下载，可能比较慢)
echo ==========================================

:: 1. 尝试安装依赖 (使用清华镜像源，速度快)
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

echo.
echo ==========================================
echo      依赖检查完毕，正在启动软件...
echo ==========================================

:: 2. 启动软件 (使用 pythonw 启动可以隐藏黑窗口，如果报错改为 python)
start "" pythonw app.py

:: 3. 退出脚本窗口
exit