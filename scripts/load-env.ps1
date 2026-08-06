# Nạp .env ở gốc repo vào biến môi trường của PHIÊN PowerShell hiện tại.
#
# backend/run.py và mcp-servers/odoo/server.py đều đọc thẳng os.environ,
# không tự nạp .env (không dùng python-dotenv) — nên trước khi chạy
# `python run.py` hoặc `python server.py` từ PowerShell, phải nạp biến môi
# trường vào phiên trước:
#
#   .\scripts\load-env.ps1
#
# Không cần dot-source (kiểm chứng thật 2026-08-06): [Environment]::
# SetEnvironmentVariable(...) không truyền EnvironmentVariableTarget ghi
# thẳng vào PROCESS block của tiến trình PowerShell hiện tại — khác biến
# PowerShell thường ($x = ...), biến môi trường KHÔNG bị giới hạn theo
# scope script, nên chạy trực tiếp hay dot-source (`. .\scripts\load-env.ps1`)
# đều cho kết quả như nhau.

Get-Content (Join-Path $PSScriptRoot "..\.env") | ForEach-Object {
    if ($_ -match '^\s*([^#=][^=]*)=(.*)$') {
        $name = $matches[1].Trim()
        $value = $matches[2].Trim()
        [System.Environment]::SetEnvironmentVariable($name, $value)
    }
}
Write-Host "Đã nạp .env vào phiên PowerShell hiện tại."