param(
    [int]$Port = 5035
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$BundledPython = "C:\Users\AJAN\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

function Test-FlaskImport {
    param([string]$PythonExe)
    if (-not (Test-Path $PythonExe)) {
        return $false
    }
    try {
        & $PythonExe -c "import flask, openpyxl" 1>$null 2>$null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

if (Test-FlaskImport $VenvPython) {
    $PythonExe = $VenvPython
} elseif (Test-FlaskImport $BundledPython) {
    $PythonExe = $BundledPython
} else {
    Write-Host "S-PULSE dependencies are not installed." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Run this once from the project folder:"
    Write-Host "  py -m venv .venv"
    Write-Host "  .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
    Write-Host ""
    Write-Host "Then start again:"
    Write-Host "  powershell -ExecutionPolicy Bypass -File .\run_dev.ps1 -Port $Port"
    exit 1
}

$env:SIPAM_PORT = [string]$Port
Set-Location $ProjectRoot
Write-Host "Starting S-PULSE on http://127.0.0.1:$Port/" -ForegroundColor Green
& $PythonExe app.py
