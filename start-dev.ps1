# start-dev.ps1 — khởi động mcp-odoo (:8003) + backend (:8002) cho dev hàng
# ngày, gói gọn lại quy trình thủ công trong docs/getting-started.md.
#
# Chạy từ thư mục gốc D:\Youdoo:
#   .\start-dev.ps1
#
# Write toggle: Odoo UI → Settings → Technical → System Parameters →
# erp_ai.write_actions_enabled
#
# KHÁC D:\Project\start-dev.ps1 một điểm có chủ đích: script đó liệt kê tay
# từng biến .env cần forward, và từng dính bug thật (2026-07-09, xem comment
# trong file đó) — thêm biến mới ở .env mà quên thêm vào danh sách khiến
# backend âm thầm fallback sai giá trị, không có cách nào phát hiện ngoài
# live-verify. Script này KHÔNG liệt kê tay: nạp TOÀN BỘ .env (giống
# scripts/load-env.ps1), forward hết — thêm biến mới ở .env tự động có tác
# dụng, không cần sửa lại script.

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$envFile = Join-Path $root ".env"
$mcpPy = Join-Path $root "mcp-servers\odoo\.venv\Scripts\python.exe"
$backendPy = Join-Path $root "backend\.venv\Scripts\python.exe"
$logDir = Join-Path $root "logs"

if (-not (Test-Path $mcpPy)) {
    Write-Host "[ERR] Thiếu $mcpPy — xem docs/getting-started.md bước 'One-time setup' #2 (tạo venv riêng cho mcp-servers/odoo)." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $backendPy)) {
    Write-Host "[ERR] Thiếu $backendPy — chạy pip install -r backend/requirements.txt trong backend/.venv trước." -ForegroundColor Red
    exit 1
}
New-Item -ItemType Directory -Force $logDir | Out-Null

Write-Host ""
Write-Host "=== Youdoo — Dev Startup ===" -ForegroundColor Cyan
Write-Host "  Write toggle: Odoo ir.config_parameter 'erp_ai.write_actions_enabled'" -ForegroundColor Gray
Write-Host ""

# ── Nạp .env vào biến môi trường của PHIÊN NÀY — forward toàn bộ, không
# liệt kê tay từng biến (xem comment đầu file). Con Start-Process bên dưới
# kế thừa environment của phiên gọi nó, nên set ở đây là đủ, không cần
# truyền -Environment riêng cho từng process. ──────────────────────────────
Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([^#=][^=]*)=(.*)$') {
        [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim())
    }
}
$env:PYTHONUTF8 = "1"   # tránh UnicodeEncodeError ở dòng "✓ ERP agent ready"

# ── Docker (postgres + open-webui + ollama) — idempotent, bỏ qua nếu docker không có
# hoặc đã chạy sẵn (restart: unless-stopped nên thường đã lên rồi). ─────────
Write-Host "[0/2] docker compose up -d (postgres + open-webui + ollama) ..." -ForegroundColor Green
# LƯU Ý: không dùng `2>&1 | Out-Null` quanh lệnh native ở đây — PowerShell
# 5.1 bọc từng dòng stderr thành NativeCommandError khi $ErrorActionPreference
# = Stop đang bật TOÀN CỤC (đầu file), dù exit code THẬT SỰ là 0 (docker CLI
# in dòng trạng thái "Container ... Running" ra stderr bình thường) — bug
# thật gặp khi viết script này 2026-08-06, sửa bằng cách tắt Stop tạm thời
# quanh lệnh native và tự kiểm tra $LASTEXITCODE thay vì dựa vào try/catch.
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
docker compose up -d
$ErrorActionPreference = $prevEap
if ($LASTEXITCODE -eq 0) {
    Write-Host "    OK (hoặc đã chạy sẵn)" -ForegroundColor Green
} else {
    Write-Host "    [WARN] docker compose exit code $LASTEXITCODE — bỏ qua, backend vẫn khởi động (chỉ Postgres/Open WebUI bị ảnh hưởng)." -ForegroundColor Yellow
}

# ── Helper: cổng đã có ai lắng nghe chưa? Tránh lặp lại đúng sự cố vừa gặp
# (chạy chồng backend cũ đang giữ cổng — bind lỗi 10048, health-check dễ bị
# hiểu nhầm là OK vì tiến trình CŨ vẫn trả lời khỏe mạnh). ──────────────────
function Test-PortOpen($port) {
    return Test-NetConnection -ComputerName "127.0.0.1" -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue
}
function Get-PortOwnerPid($port) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) { return $conn.OwningProcess }
    return $null
}

# ── mcp-odoo (:8003) ─────────────────────────────────────────────────────
$mcpPort = 8003
if (Test-PortOpen $mcpPort) {
    $ownerPid = Get-PortOwnerPid $mcpPort
    Write-Host "[1/2] :$mcpPort đã có tiến trình lắng nghe (PID $ownerPid) — bỏ qua, dùng lại." -ForegroundColor Yellow
    Write-Host "      Muốn khởi động lại sạch: Stop-Process -Id $ownerPid -Force, rồi chạy lại script." -ForegroundColor DarkGray
} else {
    Write-Host "[1/2] Khởi động mcp-odoo :$mcpPort ..." -ForegroundColor Green
    $mcpLog = Join-Path $logDir "mcp-odoo.log"
    $mcpErr = Join-Path $logDir "mcp-odoo_err.log"
    $mcp = Start-Process -FilePath $mcpPy -ArgumentList "server.py" `
        -WorkingDirectory (Join-Path $root "mcp-servers\odoo") `
        -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput $mcpLog -RedirectStandardError $mcpErr
    Write-Host "    PID $($mcp.Id) — log: logs\mcp-odoo.log"

    $sw = [Diagnostics.Stopwatch]::StartNew()
    $ok = $false
    while ($sw.Elapsed.TotalSeconds -lt 30) {
        if (Test-PortOpen $mcpPort) { $ok = $true; break }
        Start-Sleep -Milliseconds 400
    }
    if (-not $ok) {
        Write-Host "  [ERR] mcp-odoo không mở được :$mcpPort sau 30s" -ForegroundColor Red
        Get-Content $mcpErr -Tail 20
        exit 1
    }
    Write-Host "    :$mcpPort OK" -ForegroundColor Green
}

# ── backend (:8002) ──────────────────────────────────────────────────────
$backendPort = [int]([System.Environment]::GetEnvironmentVariable("BACKEND_PORT"))
if (-not $backendPort) { $backendPort = 8002 }

if (Test-PortOpen $backendPort) {
    $ownerPid = Get-PortOwnerPid $backendPort
    Write-Host "[2/2] :$backendPort đã có tiến trình lắng nghe (PID $ownerPid) — bỏ qua, dùng lại." -ForegroundColor Yellow
    Write-Host "      Muốn khởi động lại sạch: Stop-Process -Id $ownerPid -Force, rồi chạy lại script." -ForegroundColor DarkGray
    $be = $null
} else {
    Write-Host "[2/2] Khởi động backend :$backendPort ..." -ForegroundColor Green
    $beLog = Join-Path $logDir "backend.log"
    $beErr = Join-Path $logDir "backend_err.log"
    $be = Start-Process -FilePath $backendPy -ArgumentList "run.py" `
        -WorkingDirectory (Join-Path $root "backend") `
        -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput $beLog -RedirectStandardError $beErr
    Write-Host "    PID $($be.Id) — log: logs\backend.log"

    $sw = [Diagnostics.Stopwatch]::StartNew()
    $ready = $false
    while ($sw.Elapsed.TotalSeconds -lt 90) {
        try {
            $h = Invoke-RestMethod -Uri "http://localhost:$backendPort/health" -TimeoutSec 3 -ErrorAction Stop
            if ($h.agent_ready) { $ready = $true; break }
        } catch {}
        Start-Sleep -Milliseconds 700
    }
    if (-not $ready) {
        Write-Host "  [ERR] backend không sẵn sàng sau 90s" -ForegroundColor Red
        Get-Content $beErr -Tail 30
        exit 1
    }
    Write-Host "    :$backendPort OK (agent_ready = true)" -ForegroundColor Green
}

# ── Done ──────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host " Youdoo sẵn sàng!" -ForegroundColor Cyan
Write-Host ""
Write-Host " Test UI:" -ForegroundColor White
Write-Host "   http://localhost:3002 — model 'Youdoo ERP Assistant'"
Write-Host "   Xem docs/manual-test-scenarios.md để có kịch bản mẫu."
Write-Host ""
Write-Host " Logs:"
Write-Host "   mcp-odoo : logs\mcp-odoo.log  /  logs\mcp-odoo_err.log"
Write-Host "   backend  : logs\backend.log   /  logs\backend_err.log"
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

if (-not $mcp -and -not $be) {
    Write-Host "Cả hai đều đã chạy sẵn từ trước — thoát ngay, không có gì để theo dõi." -ForegroundColor DarkGray
    exit 0
}

Write-Host "Nhấn Ctrl+C để dừng các tiến trình VỪA khởi động ở trên (docker giữ nguyên)..." -ForegroundColor DarkGray
try {
    while ($true) {
        Start-Sleep -Seconds 5
        if ($mcp -and $mcp.HasExited) { Write-Host "[WARN] mcp-odoo đã thoát (exit $($mcp.ExitCode))" -ForegroundColor Yellow }
        if ($be -and $be.HasExited)  { Write-Host "[WARN] backend đã thoát (exit $($be.ExitCode))"  -ForegroundColor Yellow }
    }
} finally {
    Write-Host "`nDừng các tiến trình vừa khởi động..." -ForegroundColor DarkGray
    foreach ($p in @($be, $mcp)) {
        if ($p -and -not $p.HasExited) {
            try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch {}
        }
    }
    Write-Host "Done." -ForegroundColor DarkGray
}
