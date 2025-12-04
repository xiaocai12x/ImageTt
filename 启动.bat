@echo off
setlocal
chcp 65001 >nul
title AI OCR 启动器

cd /d "%~dp0"

echo [1/3] 正在检查环境...
if not exist "venv\Scripts\activate.bat" (
    echo 未找到虚拟环境，正在尝试创建...
    python -m venv venv
    call venv\Scripts\activate
    echo 正在安装依赖...
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
) else (
    echo 环境已存在，正在激活...
    call venv\Scripts\activate
)

echo.
echo [2/3] 正在启动软件...
echo 软件启动后，此窗口将自动关闭。
echo ========================================================

:: 核心修改点 1：使用 start "" pythonw
:: start "" : 启动一个新进程，让批处理脚本不等待它结束直接往下走
:: pythonw  : 专门用于运行 GUI 程序，不显示黑窗口
start "" pythonw app.py

:: 核心修改点 2：去掉 pause，改为 exit
exit