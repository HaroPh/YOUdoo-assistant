# Chạy hai cổng truy xuất KHÔNG tốn hạn mức API: `retrieval` và `multiturn`.
#
# Cả hai thuộc NO_LLM_SETS (backend/jobs/eval_gate.py): chỉ chạm Postgres + Ollama
# cục bộ, không một lời gọi LLM nào. Nên chạy bao nhiêu lần cũng không tốn tiền.
#
# KHI NÀO CHẠY (thứ gây hồi quy truy xuất, và vì sao không cần chạy mỗi ngày):
#   - ngay SAU mỗi lần nạp/nạp lại tài liệu hoặc `UPDATE visibility` — corpus đổi
#     ngoài git, không CI nào thấy; đây chính là thứ đã làm baseline trôi 5 tuần;
#   - TRƯỚC khi merge mã `backend/src/rag/` — CI không chạy được hai cổng này vì
#     trên CI không có Postgres, không Ollama, không corpus thật;
#   - hàng tuần qua lịch `Youdoo-CongTruyXuat-HangTuan` — lưới an toàn cho hạ tầng
#     trôi (dời Docker, đổi model Ollama, sửa .env).
#
# Chạy tay (từ bất kỳ đâu):
#   powershell -ExecutionPolicy Bypass -File D:\Youdoo\scripts\chay-cong-truy-xuat.ps1
#
# Nạp CHÍNH .env gốc qua load-env.ps1 — đúng tệp backend production đọc — nên cổng
# đo ĐÚNG cấu hình đang chạy (vd RAG_RERANK_MODE=override). Không tự dựng env riêng:
# hai nơi đọc cấu hình là cách chắc chắn để một nơi trôi mà nơi kia không biết.
#
# Mã thoát — phân biệt được "hạ tầng chưa bật" với "chất lượng tụt":
#   0 PASS · 1 cổng TRƯỢT · 2 lỗi hạ tầng giữa chừng · 3 BỎ QUA, hạ tầng chưa bật
# Mỗi lượt ghi MỘT dòng vào logs\jobs\cong-truy-xuat.log để lượt chạy theo lịch
# (cửa sổ ẩn) vẫn để lại dấu vết; JSON chi tiết nằm ở logs\jobs\eval-gate-*.json.

param(
    # Lịch hàng tuần truyền cờ này. Lịch có StartWhenAvailable nên máy tắt đúng giờ
    # thì chạy bù NGAY KHI BẬT MÁY — lúc Docker Desktop chưa kịp lên. Không chờ thì
    # tuần nào cũng ra BỎ QUA. Chạy tay thì không truyền: không ai muốn đợi 5 phút.
    [switch]$ChoHaTang
)

$ErrorActionPreference = 'Continue'   # KHÔNG 'Stop': PowerShell 5.1 biến stderr của
                                      # lệnh native thành ErrorRecord và dừng giả
$goc = Split-Path $PSScriptRoot -Parent
$logDir = Join-Path $goc 'logs\jobs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir 'cong-truy-xuat.log'
$luc = Get-Date -Format 'yyyy-MM-dd HH:mm'

function Ghi-Dong([string]$dong) {
    Add-Content -Path $log -Value $dong -Encoding UTF8
    Write-Host $dong
}

& (Join-Path $PSScriptRoot 'load-env.ps1') | Out-Null

# ── Kiểm hạ tầng TRƯỚC: thiếu thì BỎ QUA có ghi lại, không để job ra INFRA_ERROR
# lẫn vào cùng nhóm với "cổng trượt". Lịch hàng tuần trên máy dev sẽ gặp cảnh
# Docker đang tắt — đó không phải hồi quy.
function Kiem-HaTang {
    $thieu = @()
    try {
        Invoke-WebRequest -Uri "$($env:OLLAMA_URL)/api/tags" -UseBasicParsing -TimeoutSec 5 | Out-Null
    } catch { $thieu += "Ollama ($($env:OLLAMA_URL))" }
    $pg = Test-NetConnection -ComputerName 127.0.0.1 -Port 5434 -WarningAction SilentlyContinue
    if (-not $pg.TcpTestSucceeded) { $thieu += 'Postgres (127.0.0.1:5434)' }
    return ,$thieu
}
$thieu = Kiem-HaTang
if ($ChoHaTang) {
    $lan = 1
    while ($thieu.Count -gt 0 -and $lan -lt 5) {
        Start-Sleep -Seconds 60
        $thieu = Kiem-HaTang
        $lan++
    }
}
if ($thieu.Count -gt 0) {
    Ghi-Dong "$luc  BỎ QUA — hạ tầng chưa bật: $($thieu -join ', '). Bật Docker rồi chạy lại."
    exit 3
}

$py = Join-Path $goc 'backend\.venv\Scripts\python.exe'
Push-Location (Join-Path $goc 'backend')
$env:PYTHONIOENCODING = 'utf-8'
$ma = @{}
foreach ($bo in @('retrieval', 'multiturn')) {
    & $py -m jobs run eval-gate --set $bo
    $ma[$bo] = $LASTEXITCODE
}
Pop-Location

$ten = @{ 0 = 'PASS'; 1 = 'TRƯỢT'; 2 = 'LỖI HẠ TẦNG' }
$tomTat = ($ma.Keys | Sort-Object | ForEach-Object {
    $t = $ten[[int]$ma[$_]]; if (-not $t) { $t = "exit $($ma[$_])" }; "$_=$t"
}) -join '  '
$xau = ($ma.Values | Measure-Object -Maximum).Maximum
if ($xau -eq 0) { $ket = 'PASS' } elseif ($xau -eq 1) { $ket = 'CỔNG TRƯỢT' } else { $ket = 'LỖI HẠ TẦNG' }
Ghi-Dong "$luc  $tomTat  RAG_RERANK_MODE=$($env:RAG_RERANK_MODE)  → $ket"
exit $xau
