param(
    [Parameter(Position = 0)]
    [string]$Task = "help"
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

function Invoke-VenvPython {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: python $($Arguments -join ' ')"
    }
}

switch ($Task.ToLowerInvariant()) {
    "setup" {
        & python -m venv .venv
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed with exit code ${LASTEXITCODE}: python -m venv .venv"
        }
        Invoke-VenvPython @("-m", "pip", "install", "-r", "requirements.txt")
    }
    "collect" {
        Invoke-VenvPython @("-m", "collector.run_logger", "--runs", "8")
    }
    "dataset" {
        Invoke-VenvPython @("-m", "features.build_dataset")
    }
    "train" {
        Invoke-VenvPython @("-m", "model.train", "--data", "data/processed/dataset.csv")
    }
    "eval" {
        Invoke-VenvPython @("-m", "model.evaluate")
    }
    "api" {
        Invoke-VenvPython @("-m", "uvicorn", "service.app:app", "--host", "127.0.0.1", "--port", "8000")
    }
    "gui" {
        Invoke-VenvPython @("-m", "streamlit", "run", "gui/streamlit_app.py")
    }
    "test" {
        Invoke-VenvPython @("-m", "pytest", "-q")
    }
    "e2e" {
        Invoke-VenvPython @("scripts/e2e.py")
    }
    "clean" {
        $answer = Read-Host "Remove Python caches, logs, processed data, and model artifacts? (y/N)"
        if ($answer -notmatch "^(y|yes)$") {
            Write-Host "Clean cancelled."
            break
        }

        $cacheRoots = @(
            "collector",
            "features",
            "model",
            "service",
            "os_integration",
            "gui",
            "tests",
            "scripts"
        )
        $cacheDirectories = @()
        $rootCache = Join-Path $PSScriptRoot "__pycache__"
        if (Test-Path -LiteralPath $rootCache) {
            $cacheDirectories += Get-Item -LiteralPath $rootCache
        }
        foreach ($root in $cacheRoots) {
            $rootPath = Join-Path $PSScriptRoot $root
            if (Test-Path -LiteralPath $rootPath) {
                $cacheDirectories += Get-ChildItem -LiteralPath $rootPath -Directory -Filter "__pycache__" -Recurse -Force
            }
        }
        foreach ($directory in $cacheDirectories) {
            Remove-Item -LiteralPath $directory.FullName -Recurse -Force
        }

        foreach ($relativePath in @(".pytest_cache", "logs", "data/processed", "model/artifacts")) {
            $targetPath = Join-Path $PSScriptRoot $relativePath
            if (Test-Path -LiteralPath $targetPath) {
                Remove-Item -LiteralPath $targetPath -Recurse -Force
            }
        }
        Write-Host "Clean complete."
    }
    "help" {
        @"
Usage: .\tasks.ps1 <task>

Tasks:
  setup    Create .venv and install requirements
  collect  Collect 8 valid runs per configured app
  dataset  Build the processed dataset
  train    Train the resource prediction model
  eval     Evaluate the model
  api      Start the API on 127.0.0.1:8000
  gui      Start the Streamlit dashboard
  test     Run pytest
  e2e      Run the end-to-end workflow
  clean    Remove generated caches and artifacts (confirmation required)
  help     Show this list
"@
    }
    default {
        throw "Unknown task '$Task'. Run .\tasks.ps1 help for the available tasks."
    }
}
