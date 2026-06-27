<#
.SYNOPSIS
  Add kiki-compressor to your Claude Desktop config (Windows).
  Also installs the "compress-and-answer" skill to ~/.claude/skills (use --no-skill to skip).
.EXAMPLE
  ./install_claude_desktop.ps1
  ./install_claude_desktop.ps1 --dry-run          # preview, change nothing
  ./install_claude_desktop.ps1 --no-skill         # config only, no skill
  ./install_claude_desktop.ps1 --model-kind t5 --repo-dir .\attention_compressor
.NOTES
  All arguments are forwarded to add_to_claude_desktop.py (run with --help to see them).
  If scripts are blocked, run once in this shell:
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#>
$ErrorActionPreference = "Stop"

$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Prefer the project's venv Python; fall back to python / python3 on PATH.
$Py = Join-Path $Dir ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    $Py = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $Py) {
    $Py = (Get-Command python3 -ErrorAction SilentlyContinue).Source
}
if (-not $Py) {
    Write-Error "No Python found. Create the venv first:  python -m venv .venv  (see README)."
    exit 1
}

& $Py (Join-Path $Dir "add_to_claude_desktop.py") @args
exit $LASTEXITCODE
