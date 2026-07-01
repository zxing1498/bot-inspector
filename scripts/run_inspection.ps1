# Windows 定时巡检脚本
# 用法: 在「任务计划程序」中新建任务，操作指向此脚本

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    $Python = Get-Command py -ErrorAction SilentlyContinue
    if ($Python) {
        & py -3 -m src.runner --bot all --suite p0 --notify
        exit $LASTEXITCODE
    }
    Write-Error "未找到 Python，请先安装 Python 3.11+"
    exit 1
}

& python -m src.runner --bot all --suite p0 --notify
exit $LASTEXITCODE
