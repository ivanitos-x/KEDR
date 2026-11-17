$ErrorActionPreference = 'Stop'
$compiler = "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
foreach ($name in @('KEDR.exe')) {
    & $compiler /nologo /target:winexe /reference:System.Windows.Forms.dll "/out:$PSScriptRoot\$name" "$PSScriptRoot\ViewerLauncher.cs"
    if ($LASTEXITCODE -ne 0) { throw "Не удалось собрать $name" }
}
