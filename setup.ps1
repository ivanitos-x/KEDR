$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path '.venv\Scripts\python.exe')) { py -3 -m venv .venv }
& '.venv\Scripts\python.exe' -m ensurepip --upgrade
& '.venv\Scripts\python.exe' -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Установка зависимостей не завершена' }
Write-Host 'Готово. Запускайте KEDR.exe.'
& "$PSScriptRoot\build-launchers.ps1"
