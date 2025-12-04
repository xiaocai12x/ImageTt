@echo off
setlocal
chcp 65001 >nul
title AI OCR 调试模式

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
echo [2/3] 正在启动软件 (控制台模式)...
echo 如果软件闪退，请把下面的红色报错信息截图发给我！
echo ========================================================

:: 使用 python 而不是 pythonw，这样可以看到报错
python app.py

echo ========================================================
echo [3/3] 程序已结束。
pause