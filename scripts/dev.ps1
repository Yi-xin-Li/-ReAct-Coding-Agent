# 在新 PowerShell 终端中先执行：. .\scripts\dev.ps1
$env:UV_CACHE_DIR = Join-Path $PSScriptRoot '..\.cache\uv'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $PSScriptRoot '..\.tools\python'
$env:PYTHONUTF8 = '1'
