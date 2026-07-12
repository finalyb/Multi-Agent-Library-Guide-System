#!/bin/bash
# =============================================
# DGX Spark (spark-78) 一键部署脚本
# 在本地电脑上运行此脚本，通过SSH部署到云主机
# =============================================

set -e

# === DGX Spark 连接信息 ===
DGX_HOST="106.13.186.155"
DGX_PORT="6078"
DGX_USER="Developer"
DGX_PASS="rS6HJ4"
MACHINE="spark-78"

# 端口映射
INTERNAL_WEB_PORT=8888
PUBLIC_WEB_PORT=8078

echo "========================================="
echo "  吉小图 - DGX Spark 部署脚本"
echo "  机器: ${MACHINE}"
echo "  公网: ${DGX_HOST}:${DGX_PORT}"
echo "  Web端口: ${DGX_HOST}:${PUBLIC_WEB_PORT}"
echo "========================================="
echo ""

# === Step 1: 检查 SSH 连接 ===
echo "[1/5] 检查 SSH 连接..."
echo "  执行: ssh -p ${DGX_PORT} ${DGX_USER}@${DGX_HOST}"
echo ""
echo "  ⚠️  注意：请勿上传大文件，避免影响他人使用"
echo "  ⚠️  如连接失败，90%可能是内存溢出，请重启云节点"
echo ""

# === Step 2: 上传项目（仅代码，不含大文件） ===
echo "[2/5] 上传项目文件..."
echo "  请手动执行以下命令上传项目："
echo ""
echo "  # 方式1: scp 上传项目（在本地终端执行）"
echo "  scp -P ${DGX_PORT} -r C:/Users/Administrator/Desktop/Hackathon/* ${DGX_USER}@${DGX_HOST}:~/library-ai-guide/"
echo ""
echo "  # 方式2: 在远程机器上 git clone（推荐）"
echo "  ssh -p ${DGX_PORT} ${DGX_USER}@${DGX_HOST}"
echo "  git clone <your-github-url> ~/library-ai-guide"
echo "  cd ~/library-ai-guide"
echo ""

# === Step 3: 远程安装依赖 ===
echo "[3/5] 远程安装依赖..."
cat << 'REMOTE_SCRIPT'

# SSH 登录后执行以下命令：
ssh -p 6078 Developer@106.13.186.155

# --- 在远程机器上执行 ---
cd ~/library-ai-guide

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
pip install pymysql openpyxl

# 配置环境变量
cp .env.example .env
# 编辑 .env，确认STEPFUN_API_KEY已填入

# 同步馆藏数据（可选）
python scripts/sync_mysql_to_kb.py

# 构建RAG索引
python scripts/build_kb.py

REMOTE_SCRIPT

echo ""

# === Step 4: 启动服务 ===
echo "[4/5] 启动服务..."
cat << 'START_SCRIPT'

# 在远程机器上启动（注意使用8888端口——对应公网8078端口）
cd ~/library-ai-guide
source venv/bin/activate

# 前台启动（测试用）
uvicorn backend.main:app --host 0.0.0.0 --port 8888

# 后台启动（生产用）
nohup uvicorn backend.main:app --host 0.0.0.0 --port 8888 --workers 2 > server.log 2>&1 &

# 查看日志
tail -f server.log

START_SCRIPT

echo ""

# === Step 5: 验证部署 ===
echo "[5/5] 验证部署..."
echo ""
echo "  健康检查:"
echo "  curl http://${DGX_HOST}:${PUBLIC_WEB_PORT}/health"
echo ""
echo "  前端访问:"
echo "  http://${DGX_HOST}:${PUBLIC_WEB_PORT}"
echo ""
echo "========================================="
echo "  部署完成！"
echo "  公网访问地址: http://${DGX_HOST}:${PUBLIC_WEB_PORT}"
echo "========================================="

# === 内存监控提醒 ===
cat << 'MEM_WARNING'

  ⚠️  内存监控提醒：
  1. 定期检查: ssh -p 6078 Developer@106.13.186.155 'free -h'
  2. 查看进程: ssh -p 6078 Developer@106.13.186.155 'ps aux | grep uvicorn'
  3. 内存不足时: kill 掉不用的进程，或重启云节点
  4. 日志大小: du -sh ~/library-ai-guide/logs/

MEM_WARNING
