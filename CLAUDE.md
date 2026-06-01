# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Run the app

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn backend.main:app --reload
```

### Install / set up (first time)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

Or use the provided script:

```powershell
.\scripts\install_windows.ps1
```

### inklust-agent CLI (MCP/snapshot tooling)

```powershell
inklust-agent init .       # build .ai/ snapshot
inklust-agent refresh .    # re-scan after code changes
inklust-agent status .
inklust-agent grep "term" .
inklust-agent find "name" .
```

## Architecture

### Web app (`backend/` + `frontend/`)

`backend/main.py` is the entire FastAPI app — one file, no routers yet. It mounts static files at `/frontend/static` and renders Jinja2 templates from `frontend/templates/`.

Template inheritance: all pages extend `frontend/templates/base.html`, which loads the global CSS and JS. Each page overrides `{% block content %}`.

Current user flow: home page → modal (party name + display name) → `GET /fatto-party?party_name=...&username=...` (all state passed as query params, no database yet).

Static assets live in `frontend/static/` (css, js, img). The JS (`main.js`) is minimal — only modal open/close logic.

### MCP agent package (`inklust_local_agent/`)

A separate installable package (`pyproject.toml` name: `inklust-local-agent`) that exposes an MCP server for Continue + Ollama. It scans the repo and writes a machine-readable snapshot to `.ai/`. The two entry points are `inklust-agent` (CLI) and `inklust-agent-mcp` (MCP server for Continue).

This package is tooling, not part of the web app runtime.

## Key conventions

- Static files are served under the `/frontend/static` URL prefix (matches the `app.mount` path exactly).
- Query params (`party_name`, `username`) are the current mechanism for passing data between pages — no sessions or DB yet.
- Windows + PowerShell is the assumed development environment.
