$ErrorActionPreference = "Stop"

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Missing .venv. Run scripts\setup_windows.ps1 first."
}

& $python -m unittest discover -s tests -v
& $python fusion_bridge.py doctor
