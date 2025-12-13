@echo off
REM Assassyn-CPU 构建脚本 (Windows)
REM 用于构建 RV32I CPU 系统

echo ===================================
echo   Assassyn-CPU 构建工具
echo ===================================
echo.

REM 检查虚拟环境
if not defined VIRTUAL_ENV (
    echo [警告] 未检测到虚拟环境
    echo [建议] 先激活虚拟环境: .venv\Scripts\activate
    echo.
    
    REM 检查是否存在虚拟环境
    if exist .venv\Scripts\activate.bat (
        echo [提示] 发现虚拟环境，尝试激活...
        call .venv\Scripts\activate.bat
        if errorlevel 1 (
            echo [错误] 激活虚拟环境失败
            exit /b 1
        )
        echo [成功] 虚拟环境已激活
        echo.
    ) else (
        echo [警告] 继续使用系统 Python 环境...
        echo.
    )
)

REM 检查 Python
echo [检查] Python 版本...
python --version
if errorlevel 1 (
    echo [错误] 未找到 Python
    echo [提示] 请先安装 Python 3.10 或更高版本
    exit /b 1
)
echo.

REM 创建工作目录
echo [准备] 工作目录...
if not exist .workspace mkdir .workspace
echo [成功] 工作目录已创建: .workspace\
echo.

REM 运行构建
echo [开始] 构建 CPU 系统...
echo.

python -m src.main

if errorlevel 1 (
    echo.
    echo ===================================
    echo   [失败] 构建过程出现错误
    echo ===================================
    exit /b 1
)

echo.
echo ===================================
echo   [成功] 构建完成！
echo ===================================
