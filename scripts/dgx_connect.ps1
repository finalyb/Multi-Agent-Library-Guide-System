# =============================================
# DGX Spark (spark-78) Windows 快速操作脚本
# =============================================

$DGX_HOST = "106.13.186.155"
$DGX_PORT = "6078"
$DGX_USER = "Developer"
$DGX_PASS = "rS6HJ4"
$MACHINE = "spark-78"
$PUBLIC_WEB_PORT = "8078"
$INTERNAL_WEB_PORT = "8888"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  吉小图 - DGX Spark (spark-78) 操作面板" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  公网访问: http://${DGX_HOST}:${PUBLIC_WEB_PORT}" -ForegroundColor Green
Write-Host "  SSH 连接: ssh -p ${DGX_PORT} ${DGX_USER}@${DGX_HOST}" -ForegroundColor Green
Write-Host ""
Write-Host "  选择操作:" -ForegroundColor Yellow
Write-Host "  1) SSH 连接云主机"
Write-Host "  2) 检查服务健康状态"
Write-Host "  3) 查看远程内存使用"
Write-Host "  4) 启动服务（需先SSH登录）"
Write-Host "  5) 通过scp上传项目文件"
Write-Host "  0) 退出"
Write-Host ""

$choice = Read-Host "请输入选项"

switch ($choice) {
    "1" {
        Write-Host "正在连接 SSH..." -ForegroundColor Green
        Write-Host "密码: ${DGX_PASS}" -ForegroundColor Yellow
        ssh -p $DGX_PORT "${DGX_USER}@${DGX_HOST}"
    }
    "2" {
        Write-Host "检查健康状态..." -ForegroundColor Green
        try {
            $response = Invoke-WebRequest -Uri "http://${DGX_HOST}:${PUBLIC_WEB_PORT}/health" -TimeoutSec 10
            Write-Host $response.Content -ForegroundColor Green
        } catch {
            Write-Host "❌ 服务不可达: $_" -ForegroundColor Red
        }
    }
    "3" {
        Write-Host "检查远程内存..." -ForegroundColor Green
        ssh -p $DGX_PORT "${DGX_USER}@${DGX_HOST}" "free -h; echo ''; echo '进程列表:'; ps aux --sort=-%mem | head -10"
    }
    "4" {
        Write-Host "在远程机器上启动服务..." -ForegroundColor Green
        Write-Host "请确保项目已上传到 ~/library-ai-guide" -ForegroundColor Yellow
        ssh -p $DGX_PORT "${DGX_USER}@${DGX_HOST}" @"
cd ~/library-ai-guide
source venv/bin/activate
nohup uvicorn backend.main:app --host 0.0.0.0 --port ${INTERNAL_WEB_PORT} --workers 2 > server.log 2>&1 &
echo "服务已后台启动，PID: $!"
echo "日志: tail -f ~/library-ai-guide/server.log"
"@
    }
    "5" {
        Write-Host "上传项目文件（排除大文件）..." -ForegroundColor Green
        $localPath = "C:\Users\Administrator\Desktop\Hackathon\"
        Write-Host "仅上传代码文件（跳过 data/chroma_db, __pycache__, .git）"
        # 使用 rsync 替代（如已安装）
        Write-Host "手动执行: scp -P ${DGX_PORT} -r .\* ${DGX_USER}@${DGX_HOST}:~/library-ai-guide/"
    }
    "0" {
        Write-Host "再见！" -ForegroundColor Gray
    }
    default {
        Write-Host "无效选项" -ForegroundColor Red
    }
}
