#Requires -Version 5.1
<#
.SYNOPSIS
  One-command stand-up of the carshorts stack on a Windows machine (incl. a
  brand-new laptop). Idempotent: safe to re-run; skips whatever is already there.

.DESCRIPTION
  Installs Python 3.12, ffmpeg, Node LTS, and the claude CLI; builds the venv and
  installs the package; sets PYTHONUTF8 and puts ffmpeg on PATH persistently;
  registers the daily scheduled tasks; then runs a smoke test (ruff + pytest).

  It NEVER touches your secrets or uploads anything. At the end it prints exactly
  what only you can do (drop in .env / OAuth files / assets, authenticate agents).

.PARAMETER SkipInstall  Skip the winget/npm installs (tools already present).
.PARAMETER SkipTasks    Skip registering the scheduled tasks.
.PARAMETER Time         Daily heartbeat time HH:mm (default 08:00); watch runs +1h.

.EXAMPLE
  .\tools\setup.ps1
#>
[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [switch]$SkipTasks,
    [string]$Time = "08:00"
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo
$script:ok = @(); $script:warn = @(); $script:todo = @()

function Say($m)  { Write-Host "==> $m" -ForegroundColor Cyan }
function Good($m) { Write-Host "  [ok]   $m" -ForegroundColor Green;  $script:ok += $m }
function Warn($m) { Write-Host "  [warn] $m" -ForegroundColor Yellow; $script:warn += $m }
function Have($name) { [bool](Get-Command $name -ErrorAction SilentlyContinue) }

function Install-Pkg($id) {
    # msstore source has intermittent cert issues; pin to the winget source.
    $wargs = @("install", "--id", $id, "-e", "--source", "winget", "--silent",
               "--accept-package-agreements", "--accept-source-agreements")
    & winget @wargs 2>&1 | Out-Null
}

function PyVersion {
    if (-not (Have python)) { return "" }
    try { return (& python --version 2>&1 | Out-String).Trim() } catch { return "" }
}

Write-Host ""
Say "carshorts setup - repo: $Repo"
Write-Host ""

# --- 0. prerequisites ------------------------------------------------------
if (-not (Have winget)) {
    throw "winget not found. Install 'App Installer' from the Microsoft Store, then re-run."
}

# --- 1. system tools -------------------------------------------------------
if (-not $SkipInstall) {
    Say "System tools (Python, ffmpeg, Node, claude CLI)"

    if ((PyVersion) -like "Python 3.*") { Good "Python present: $(PyVersion)" }
    else { Write-Host "  installing Python 3.12..."; Install-Pkg "Python.Python.3.12"; Good "Python 3.12 installed" }

    if (Have ffmpeg) { Good "ffmpeg present" }
    else { Write-Host "  installing ffmpeg..."; Install-Pkg "Gyan.FFmpeg"; Good "ffmpeg installed" }

    if (Have node) { Good "Node present" }
    else { Write-Host "  installing Node LTS..."; Install-Pkg "OpenJS.NodeJS.LTS"; Good "Node installed" }

    # claude CLI via npm (needs npm on PATH; a fresh Node install may require a
    # new shell before npm resolves)
    if (Have claude) { Good "claude CLI present" }
    elseif (Have npm) {
        Write-Host "  installing claude CLI..."
        & npm install -g "@anthropic-ai/claude-code" 2>&1 | Out-Null
        if (Have claude) { Good "claude CLI installed" }
        else { Warn "claude CLI installed but not yet on PATH - open a new shell and re-run to confirm" }
    }
    else { Warn "npm not on PATH yet (Node just installed) - open a NEW shell and re-run setup to finish the claude CLI" }
} else { Say "Skipping installs (-SkipInstall)" }

# --- 2. ffmpeg on the persistent PATH --------------------------------------
Say "ffmpeg on PATH"
if (Have ffmpeg) { Good "ffmpeg already resolvable" }
else {
    $ff = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Filter ffmpeg.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($ff) {
        $bin = Split-Path $ff.FullName
        $userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
        if ($userPath -notlike "*$bin*") {
            [Environment]::SetEnvironmentVariable("PATH", "$bin;$userPath", "User")
        }
        $env:PATH = "$bin;$env:PATH"
        Good "ffmpeg bin added to user PATH: $bin"
        Warn "open a NEW shell for the PATH change to take effect everywhere"
    } else { Warn "could not locate ffmpeg.exe - install it or add its bin to PATH manually" }
}

# --- 3. UTF-8 mode (the cp1252 mojibake fix) -------------------------------
Say "PYTHONUTF8 (Windows cp1252 fix for the rupee glyph etc.)"
if ([Environment]::GetEnvironmentVariable("PYTHONUTF8", "User") -eq "1") { Good "PYTHONUTF8 already set" }
else { [Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "User"); $env:PYTHONUTF8 = "1"; Good "PYTHONUTF8=1 set (user)" }

# --- 4. venv + package -----------------------------------------------------
Say "Python virtual environment + dependencies"
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & python -m venv .venv
    Good "created .venv"
} else { Good ".venv already present" }
$venvPy = ".\.venv\Scripts\python.exe"
& $venvPy -m pip install --upgrade pip -q
& $venvPy -m pip install -e ".[dev,video,crawl,publish,real]" -q
Good "installed carshorts with all extras"

# --- 5. scheduled tasks (the daily heartbeat) ------------------------------
if (-not $SkipTasks) {
    Say "Daily scheduled tasks"
    $hb = Join-Path $Repo "tools\heartbeat.cmd"
    $rw = Join-Path $Repo "tools\retention_watch.cmd"
    $t2 = ([datetime]::ParseExact($Time, "HH:mm", $null)).AddHours(1).ToString("HH:mm")
    & schtasks /create /tn "carshorts-heartbeat" /tr "'$hb'" /sc DAILY /st $Time /f 2>&1 | Out-Null
    & schtasks /create /tn "carshorts-retention-watch" /tr "'$rw'" /sc DAILY /st $t2 /f 2>&1 | Out-Null
    Good "registered carshorts-heartbeat ($Time) + carshorts-retention-watch ($t2)"
    Warn "the heartbeat NEVER publishes - it only prepares a draft for your Gate 1 review"
} else { Say "Skipping scheduled tasks (-SkipTasks)" }

# --- 6. smoke test ---------------------------------------------------------
Say "Smoke test (ruff + pytest, offline)"
& $venvPy -m ruff check . 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) { Good "ruff clean" } else { Warn "ruff reported issues (run: .\.venv\Scripts\ruff.exe check .)" }
$pt = (& $venvPy -m pytest -q 2>&1 | Select-Object -Last 1)
Write-Host "  pytest: $pt"
if ($LASTEXITCODE -eq 0) { Good "pytest green" } else { Warn "pytest failed - ensure ffmpeg is on PATH in this shell, then retry" }

# --- 7. what only you can do -----------------------------------------------
if (-not (Test-Path ".env"))               { $script:todo += "Create .env (copy .env.example): GROQ_API_KEY, GEMINI_API_KEY, PEXELS_API_KEY. Add ANTHROPIC_API_KEY to enable agents." }
if (-not (Test-Path "client_secret.json")) { $script:todo += "Add client_secret.json + youtube_token.json for uploads/analytics (Google OAuth - see publish.py)." }
if (-not (Test-Path "assets\cars"))        { $script:todo += "Populate assets/ (curated car pools, fonts, music) - the render pool is otherwise empty." }
if (Have claude) {
    $auth = (& claude -p "PONG" --output-format json --max-turns 1 2>&1 | Out-String)
    if ($auth -match "Not logged in") { $script:todo += "Authenticate claude ('claude' then /login) OR set ANTHROPIC_API_KEY, to enable the scriptwright/curator agents." }
}

Write-Host ""
Say "SUMMARY"
Write-Host ("  {0} step(s) ok, {1} warning(s)" -f $script:ok.Count, $script:warn.Count)
foreach ($w in $script:warn) { Write-Host "  ! $w" -ForegroundColor Yellow }
if ($script:todo.Count) {
    Write-Host ""
    Write-Host "  YOUR TO-DO (only you can do these):" -ForegroundColor Magenta
    foreach ($t in $script:todo) { Write-Host "   - $t" -ForegroundColor Magenta }
}
Write-Host ""
Write-Host "  Verify state:  .\.venv\Scripts\python.exe -m carshorts.orchestration.heartbeat --status" -ForegroundColor Cyan
Write-Host "  Review portal: .\.venv\Scripts\python.exe -m carshorts.portal   (http://localhost:8787)" -ForegroundColor Cyan
Write-Host ""
exit 0   # status is reported above; don't leak a probe's non-zero exit code
