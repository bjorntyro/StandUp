$ErrorActionPreference = "Stop"

Write-Host "== InkLust Local Agent installer =="

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python was not found in PATH. Install Python 3.11+ first."
}

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    throw "Ollama was not found in PATH. Install Ollama first."
}

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

$pythonExe = Join-Path (Resolve-Path ".venv").Path "Scripts\python.exe"
$projectRoot = (Resolve-Path ".").Path

& $pythonExe -m pip install --upgrade pip
& $pythonExe -m pip install -e .

if (-not (Test-Path ".continue")) {
    New-Item -ItemType Directory -Path ".continue" | Out-Null
}
if (-not (Test-Path ".continue\rules")) {
    New-Item -ItemType Directory -Path ".continue\rules" | Out-Null
}
if (-not (Test-Path ".continue\prompts")) {
    New-Item -ItemType Directory -Path ".continue\prompts" | Out-Null
}
if (-not (Test-Path ".continue\mcpServers")) {
    New-Item -ItemType Directory -Path ".continue\mcpServers" | Out-Null
}

Copy-Item ".continue\config.yaml" ".continue\config.yaml" -Force
Copy-Item ".continue\rules\inklust-local-agent-rule.md" ".continue\rules\inklust-local-agent-rule.md" -Force
Copy-Item ".continue\prompts\init-project.md" ".continue\prompts\init-project.md" -Force
Copy-Item ".continue\prompts\refresh-project.md" ".continue\prompts\refresh-project.md" -Force
Copy-Item ".continue\prompts\investigate-bug.md" ".continue\prompts\investigate-bug.md" -Force
Copy-Item ".continue\mcpServers\inklust-local-agent.yaml" ".continue\mcpServers\inklust-local-agent.yaml" -Force

& $pythonExe -m inklust_local_agent.cli init $projectRoot

Write-Host "Installation complete."
Write-Host "Open Continue in this project and run /init-project"
