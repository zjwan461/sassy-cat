@echo off
chcp 65001 >nul
title 臭屁猫 - Development

echo ==========================================
echo   Electron + Python + Vue3 脚手架
echo ==========================================
echo.

REM 检查 Node.js
where node >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 未找到 Node.js，请先安装 Node.js
    pause
    exit /b 1
)

REM 检查 npm
where npm >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 未找到 npm，请先安装 npm
    pause
    exit /b 1
)

echo [信息] Node.js 版本:
node --version
echo.

REM 检查 node_modules 是否存在
if not exist "node_modules\" (
    echo [信息] 首次运行，正在安装依赖...
    call npm install
    if %errorlevel% neq 0 (
        echo [错误] 依赖安装失败
        pause
        exit /b 1
    )
    echo [成功] 依赖安装完成
    echo.
)

echo [信息] 启动开发环境...
echo.
call npm run electron:dev

pause
