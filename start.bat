@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   算法竞赛辅导智能体 ARENA  启动中...
echo ============================================================
echo.

rem 默认 python 可能是 2.7，这里优先用 Anaconda 的 Python 3
set "PY=D:\Anaconda3\python.exe"
if not exist "%PY%" set "PY=python"

"%PY%" -X utf8 run.py

echo.
echo 服务已停止。按任意键关闭窗口。
pause >nul
