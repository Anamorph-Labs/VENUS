# Venus in one step, on Windows (PowerShell):   powershell -ExecutionPolicy Bypass -File install.ps1
#
# 1. checks for Python 3.10+ and FFmpeg (and installs FFmpeg with winget when it is missing);
# 2. puts Venus in its own folder (%USERPROFILE%\.venus) so nothing else changes;
# 3. downloads the free models once (Whisper to hear; add -Find for footage search);
# 4. runs `alvenus doctor` to show that everything works.
#
# Nothing is uploaded. Run it again any time to update.
param([switch]$Small, [switch]$Find, [switch]$NoModels)
$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$HomeDir = if ($env:VENUS_HOME) { $env:VENUS_HOME } else { Join-Path $env:USERPROFILE ".venus" }
$Model = if ($Small) { "base.en" } else { "small.en" }

Write-Host "`n== Python"
$Py = $null
foreach ($c in @("py -3", "python3", "python")) {
  try {
    $parts = $c.Split(" ")
    & $parts[0] $parts[1..($parts.Length - 1)] -c "import sys; sys.exit(sys.version_info < (3, 10))" 2>$null
    if ($LASTEXITCODE -eq 0) { $Py = $parts; break }
  } catch {}
}
if (-not $Py) { Write-Host "Venus needs Python 3.10 or newer: https://www.python.org/downloads/ (then run this again)"; exit 1 }
& $Py[0] $Py[1..($Py.Length - 1)] --version

Write-Host "`n== FFmpeg"
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    Write-Host "FFmpeg is missing; installing it with winget"
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
    Write-Host "Close this window and open a new one so FFmpeg is found, then run this again."; exit 0
  } else { Write-Host "Please install FFmpeg (https://ffmpeg.org/download.html), then run this again."; exit 1 }
}
ffmpeg -version | Select-Object -First 1

Write-Host "`n== Venus"
$VPy = Join-Path $HomeDir "Scripts\python.exe"
if (-not (Test-Path $VPy)) { & $Py[0] $Py[1..($Py.Length - 1)] -m venv $HomeDir }
& $VPy -m pip install --quiet --upgrade pip
& $VPy -m pip install --quiet --upgrade $Here
$Scripts = Join-Path $HomeDir "Scripts"
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($UserPath -notlike "*$Scripts*") {
  [Environment]::SetEnvironmentVariable("Path", "$UserPath;$Scripts", "User")
  Write-Host "added $Scripts to your PATH (open a new window to use the alvenus command)"
}
$Venus = Join-Path $Scripts "alvenus.exe"

if (-not $NoModels) {
  Write-Host "`n== Models (once)"
  if ($Find) { & $Venus fetch-models --model $Model --find } else { & $Venus fetch-models --model $Model }
}

Write-Host "`n== Check"
& $Venus doctor
Write-Host "`nDone. Start with:  alvenus studio    (describe your video, read the storyboard, press Render)"
