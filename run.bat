@echo off

REM 定义目录路径
set "REPO_PARENT_PATH=C:\Users\Administrator\Desktop"
set "REPO_PATH=C:\Users\Administrator\Desktop\MediaCrawler"

REM 判断文件夹是否存在
if exist "%REPO_PATH%" (
    REM 获取最新代码
    cd "%REPO_PATH%"
    git pull
) else (
    REM 文件夹不存在，进入上级目录并克隆仓库
    cd "%REPO_PARENT_PATH%"
    git clone https://github.com/msli121/MediaCrawler.git
    cd MediaCrawler
)

REM 环境检查
where conda >nul 2>nul
if %errorlevel% neq 0 (
    echo Conda could not be found. Please install Miniconda or Anaconda first.
    exit /b 1
)

REM 设置和激活conda环境
call :setup_env
if %errorlevel% neq 0 (
    exit /b 1
)
call :start_app
exit /b 0

REM 函数来创建和激活conda环境
:setup_env
REM 检查 media-crawler 环境是否存在
call conda env list | findstr /b /c:"media-crawler" >nul
if %errorlevel% neq 0 (
    echo Creating 'media-crawler' environment...
    call conda create --name media-crawler python=3.9 -y
) else (
    echo Environment 'media-crawler' already exists.
)
REM 激活环境
call conda activate media-crawler
if %errorlevel% neq 0 (
    call conda init cmd.exe
    call conda activate media-crawler
)
if %errorlevel% neq 0 (
    echo Failed to activate conda environment.
    exit /b 1
)
echo Conda environment 'media-crawler' has been activated.
REM 安装依赖包
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
if %errorlevel% neq 0 (
    echo Failed to install dependencies.
    exit /b 1
)
echo Dependencies have been installed.
REM 返回主流程
goto :eof

REM 函数来启动应用程序
:start_app
python api_server.py
if %errorlevel% neq 0 (
    echo Failed to start application.
    exit /b 1
)
echo Run server successfully.
REM 返回主流程
goto :eof