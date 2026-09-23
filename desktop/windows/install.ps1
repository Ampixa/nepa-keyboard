$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$BuildScript = Join-Path $Root "tools\build_windows_pime.py"
python $BuildScript

$PimeRoot = Join-Path ${env:ProgramFiles(x86)} "PIME"
$InputMethods = Join-Path $PimeRoot "python\input_methods"
if (-not (Test-Path $InputMethods)) {
    throw "PIME is not installed. Install PIME 1.3 or newer, then run this script again."
}

$Overlay = Join-Path $Root "desktop\windows\build\PIME\python\input_methods"
Get-ChildItem $Overlay -Directory | ForEach-Object {
    Copy-Item $_.FullName -Destination $InputMethods -Recurse -Force
}

Write-Host "Installed Nepali, Nepal Bhasa/Newa, and Limbu Nepa phonetic services."
Write-Host "Restart PIME or sign out, then add the desired keyboard in Windows Settings."

