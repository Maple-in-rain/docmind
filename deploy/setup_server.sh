#!/usr/bin/env bash
# DocMind 一键部署（Ubuntu 22.04/24.04，2C2G 学生机，无 GPU）
# 用法（以普通用户 ubuntu 登录服务器后）：
#   git clone https://github.com/Maple-in-rain/docmind.git   # 或下载本仓库的 deploy/ 目录
#   bash docmind/deploy/setup_server.sh
set -euo pipefail

PROJECT_DIR="$HOME/docmind"
CONDA_DIR="$HOME/miniconda3"
# 中国区服务器 clone GitHub 不稳时二选一：
#   1) Gitee 镜像仓库（需自行 push 一份，把地址换掉）
#   2) 加速代理：https://ghproxy.com/https://github.com/Maple-in-rain/docmind.git
GIT_REPO="https://github.com/Maple-in-rain/docmind.git"

echo "==> [1/5] 基础依赖"
sudo apt-get update -y && sudo apt-get install -y git curl wget unzip

echo "==> [2/5] Miniconda（清华镜像，已装则跳过）"
if [ ! -d "$CONDA_DIR" ]; then
  curl -fsSL https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-latest-Linux-x86_64.sh -o /tmp/miniconda.sh
  bash /tmp/miniconda.sh -b -p "$CONDA_DIR"
fi
source "$CONDA_DIR/etc/profile.d/conda.sh"

echo "==> [3/5] conda 环境 + 代码 + 依赖（pip 清华镜像）"
conda create -n docmind python=3.12 -y
conda activate docmind
if [ ! -d "$PROJECT_DIR/.git" ]; then
  git clone "$GIT_REPO" "$PROJECT_DIR"
else
  cd "$PROJECT_DIR" && git pull --ff-only || true
fi
cd "$PROJECT_DIR"
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

echo "==> [4/5] .env 配置（人工步骤）"
if [ ! -f .env ]; then
  cp .env.example .env
fi
echo ">>> 请编辑 $PROJECT_DIR/.env 填入 DEEPSEEK_API_KEY / SILICONFLOW_API_KEY，完成后回车继续"
read -r _

echo "==> [5/5] systemd + nginx + swap"
sudo cp deploy/docmind.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now docmind
sudo apt-get install -y nginx
sudo cp deploy/nginx.conf /etc/nginx/sites-available/docmind
sudo ln -sf /etc/nginx/sites-available/docmind /etc/nginx/sites-enabled/docmind
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

# 2G 内存加 2G swap（pip 装 chromadb 与运行期防 OOM）
if ! grep -q swapfile /etc/fstab; then
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

echo ">>> 部署完成：http://<服务器公网IP>/（云控制台安全组需放行 80 端口）"
echo ">>> 排查：journalctl -u docmind -f  |  sudo nginx -t"
