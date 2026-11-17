param(
    [ValidatePattern('^\d+\.\d+\.\d+$')][string]$Version = '1.0.0',
    [string]$Python = "$PSScriptRoot\.venv\Scripts\python.exe",
    [string]$Iscc = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
$ErrorActionPreference = 'Stop'
$Python = (Resolve-Path -LiteralPath $Python).Path
$Iscc = (Resolve-Path -LiteralPath $Iscc).Path
Push-Location -LiteralPath $PSScriptRoot
try {
    & $Python -m PyInstaller --noconfirm --clean --windowed --onedir --name KEDR --specpath .test-tmp/pyinstaller --workpath .test-tmp/build --distpath .test-tmp/dist launch.py
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
    # Qt 6.10 on Windows imports the system ICU ABI. A build host's newer ICU
    # can be collected ahead of it and make QtCore fail to load.
    Get-ChildItem -LiteralPath .test-tmp/dist/KEDR/_internal -File |
        Where-Object { $_.Name -eq 'icuuc.dll' -or $_.Name -like 'icudt*.dll' } |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName }
    & $Python packaging/collect_notices.py .test-tmp/dist/KEDR/licenses
    if ($LASTEXITCODE -ne 0) { throw 'Could not assemble third-party notices' }
    & $Iscc "/DAppVersion=$Version" packaging/KEDR.iss
    if ($LASTEXITCODE -ne 0) { throw 'Inno Setup failed' }
} finally { Pop-Location }
