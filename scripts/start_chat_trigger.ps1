$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

Write-Host "启动飞书群内巡检监听（长连接）..."
Write-Host "在测试群发送: 巡检 / 巡检 p0 / 巡检 full"
Write-Host "按 Ctrl+C 停止"
Write-Host ""

python -m src.chat_trigger
