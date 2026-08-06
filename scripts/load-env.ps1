# Nạp .env ở gốc repo vào biến môi trường của PHIÊN PowerShell hiện tại.
#
# backend/run.py và mcp-servers/odoo/server.py đều đọc thẳng os.environ,
# không tự nạp .env (không dùng python-dotenv) — nên trước khi chạy
# `python run.py` hoặc `python server.py` từ PowerShell, phải nạp biến môi
# trường vào phiên trước, dot-source file này:
#
#   . .\scripts\load-env.ps1
#
# (dấu chấm đầu dòng bắt buộc — chạy trực tiếp `.\scripts\load-env.ps1`
# không có dấu chấm sẽ set biến trong PROCESS CON, biến mất ngay khi script
# kết thúc, không ích gì cho các lệnh chạy SAU trong cùng phiên.)

Get-Content (Join-Path $PSScriptRoot "..\.env") | ForEach-Object {
    if ($_ -match '^\s*([^#=][^=]*)=(.*)$') {
        $name = $matches[1].Trim()
        $value = $matches[2].Trim()
        [System.Environment]::SetEnvironmentVariable($name, $value)
    }
}
Write-Host "Đã nạp .env vào phiên PowerShell hiện tại."
