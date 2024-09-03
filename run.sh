#!/bin/bash

# 获取最新代码
cd /root/MediaCrawler
git pull
#rm -fr /root/MediaCrawler
#cd /root && git clone https://github.com/msli121/MediaCrawler.git

# 检查conda命令是否存在
if ! command -v conda &> /dev/null; then
    echo "Conda could not be found. Please install Miniconda or Anaconda first."
    exit 1
fi

# 函数来创建和激活conda环境
setup_conda_env() {
    # 检查 media-crawler 环境是否存在
    if conda info --envs | grep -q "^media-crawler"; then
        echo "Environment 'media-crawler' already exists."
    else
        echo "Creating 'media-crawler' environment..."
        conda create --name media-crawler python=3.9 -y
    fi

    # 激活环境
    # source $(conda info --base)/etc/profile.d/conda.sh
    conda activate media-crawler

    echo "Conda environment 'media-crawler' has been activated."

    # 安装依赖包
    pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

    echo "Dependencies have been installed."
}

# 函数来启动应用程序
start_app() {
    nohup python api_server.py > output.log 2>&1 &
    echo $! > app.pid
    echo "Run server successfully. Check 'output.log' for details."
}

# 函数来停止应用程序
stop_app() {
    if [ -f app.pid ]; then
        kill $(cat app.pid)
        rm app.pid
        echo "The application has been stopped."
    else
        echo "No application is running."
    fi
}

# 解析命令行参数
ACTION=$1
case $ACTION in
    start)
        setup_conda_env
        start_app
        ;;
    stop)
        stop_app
        ;;
    restart)
        stop_app
        setup_conda_env
        start_app
        ;;
    *)
        echo "Usage: $0 {start|stop|restart}"
        exit 1
        ;;
esac