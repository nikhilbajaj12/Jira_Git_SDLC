param(
    [ValidateSet("run", "install", "test", "lint", "format", "help")]
    [string]$Command = "help"
)

$VENV_PYTHON = Join-Path $PSScriptRoot ".venv" "Scripts" "python.exe"
$VENV_UV = Join-Path $PSScriptRoot ".venv" "Scripts" "uv.exe"

function Ensure-Venv {
    if (-not (Test-Path $VENV_PYTHON)) {
        Write-Host "Creating virtual environment..." -ForegroundColor Yellow
        python -m venv (Join-Path $PSScriptRoot ".venv")
    }
}

function Invoke-Install {
    Ensure-Venv
    Write-Host "Installing dependencies..." -ForegroundColor Green
    python -m uv sync --python $VENV_PYTHON
    python -m uv pip install -e ".[dev]" --python $VENV_PYTHON
}

function Invoke-Run {
    Write-Host "Starting server on http://localhost:8000..." -ForegroundColor Green
    & $VENV_PYTHON -m uvicorn agent.webapp:app --reload --port 8000 --env-file .env
}

function Invoke-Lint {
    & $VENV_PYTHON -m ruff check $PSScriptRoot
    & $VENV_PYTHON -m ruff format $PSScriptRoot --diff
}

function Invoke-Format {
    & $VENV_PYTHON -m ruff format $PSScriptRoot
    & $VENV_PYTHON -m ruff check --fix $PSScriptRoot
}

function Invoke-Test {
    param([string]$TestPath = "tests/")
    & $VENV_PYTHON -m pytest -vvv $TestPath
}

function Show-Help {
    Write-Host @"
Open SWE Dev Script (PowerShell)
Usage: .\dev.ps1 <command>

Commands:
  run         Start the FastAPI server on port 8000
  install     Install/update dependencies
  test        Run tests (optional: -TestPath tests/test_file.py)
  lint        Run ruff linter and format check
  format      Auto-format code with ruff
  help        Show this help
"@
}

switch ($Command) {
    "run"     { Invoke-Run }
    "install" { Invoke-Install }
    "test"    { Invoke-Test }
    "lint"    { Invoke-Lint }
    "format"  { Invoke-Format }
    "help"    { Show-Help }
}
