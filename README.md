# InkLust Local Agent

A local coding workflow for **Continue + Ollama** that gives your model a repeatable way to understand an InkLust-style project without manual copy/paste every session.

This setup is designed for:

- Windows development
- FastAPI + Jinja2 + Uvicorn
- SQLite during the early growth phase
- strict "read the real files first" behavior
- a manual re-scan command when the code changes

## What this system does

This package gives you three layers working together:

1. **Continue** inside VS Code or PyCharm.
2. **Ollama** as the local model runtime.
3. **A local MCP server** that can scan the current repository, build a project snapshot, search files, list routes, and re-read the project when you ask.

It does **not** magically stuff every file of a project into one single prompt forever. That would break on context limits. Instead, it builds a local snapshot and gives Continue tools to inspect the repository on demand. This is the practical way to get a "Claude Code style" flow locally.

## What gets created in each project

After initialization, the project gets a local `.ai/` folder:

- `.ai/project_snapshot.json` → machine-readable snapshot of indexed files
- `.ai/project_context.md` → human-readable project briefing
- `.ai/file_tree.txt` → tree preview of the repository
- `.ai/session_log.md` → refresh history

These files help the model start from a grounded overview and then drill into exact source files when needed.

## How to install on Windows

### 1. Requirements

You need:

- Python 3.11+
- Ollama running on Windows
- Continue installed in VS Code or JetBrains
- your model already pulled locally, for example:

```powershell
ollama pull qwen3:8b
```

Ollama on Windows serves its local API at `http://localhost:11434`. Continue can connect directly to Ollama models, and MCP servers can be configured in `config.yaml`. citeturn648342search6turn458307view0

### 2. Put this package in your project root

Copy the contents of this folder into the root of your FastAPI project.

Expected root example:

```text
InkLust/
├── backend/
├── frontend/
├── alembic/
├── .continue/
├── inklust_local_agent/
├── pyproject.toml
└── README.md
```

### 3. Create or use your virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

This installs the MCP server entry points:

- `inklust-agent`
- `inklust-agent-mcp`

### 4. Confirm Ollama works

```powershell
ollama list
ollama run qwen3:8b
```

### 5. Make Continue use the workspace config

The included `.continue/config.yaml` defines:

- `qwen3:8b` as the local chat/edit model
- file/code/diff/terminal context providers
- the local MCP server
- rules and prompts for init, refresh, and bug investigation

Continue supports local `config.yaml`, local rules, local prompts, and MCP servers in the same config. citeturn458307view0turn199594search2

### 6. Initialize the snapshot once

From the project root:

```powershell
inklust-agent init .
```

This creates the `.ai/` folder and scans the current project.

## Daily usage

### First message in a fresh session

In Continue chat, say one of these:

- `initialize this project`
- `/init-project`

The agent rule tells the model to call `init_project` first, then fetch the briefing.

### After you changed code manually

Say either:

- `read the project again to be aligned with the current state of the code`
- `/refresh-project`

That triggers a full re-scan through the MCP tool.

### When debugging

Example:

```text
why does the function post("/my-stories") break? investigate and find out
```

A good run should look like this internally:

1. inspect the snapshot
2. locate the route
3. read the exact Python file
4. read related templates or JS
5. explain the real cause
6. propose the smallest safe fix

## Commands you can run manually in PowerShell

### Initialize snapshot

```powershell
inklust-agent init .
```

### Refresh snapshot

```powershell
inklust-agent refresh .
```

### Show status

```powershell
inklust-agent status .
```

### Search for a symbol or route

```powershell
inklust-agent grep "my-stories" .
```

### Find files by name

```powershell
inklust-agent find "story" .
```

## MCP tools exposed to Continue

The local MCP server exposes these tools:

- `init_project`
- `refresh_project`
- `get_project_briefing`
- `list_project_files`
- `inspect_routes`
- `read_project_file_tool`
- `grep_project_tool`
- `find_files_tool`

The MCP standard exists specifically to let AI clients connect to external tools and data sources, and Continue supports MCP servers from `config.yaml`. citeturn301665search0turn199594search2turn458307view0

## Files that matter most

### `.continue/config.yaml`
This is the central Continue configuration.

### `.continue/rules/inklust-local-agent-rule.md`
This enforces your project behavior, including:

- Windows assumptions
- FastAPI + Jinja2 + Uvicorn assumptions
- SQLite default
- English-only code comments
- never guessing the code when a real file can be read

### `.continue/prompts/*.md`
These give you slash commands:

- `/init-project`
- `/refresh-project`
- `/investigate-bug`

### `inklust_local_agent/project_scanner.py`
This scans the repository and builds the `.ai` snapshot.

### `inklust_local_agent/mcp_server.py`
This exposes the scanner as an MCP server for Continue.

## What the scanner reads

The scanner deeply indexes text files such as:

- Python
- HTML/Jinja templates
- CSS
- JS
- JSON
- TOML
- YAML
- Markdown
- config files

It skips binary assets like images, font files, PDFs, and SQLite database files.

It also skips directories like:

- `.git`
- `.venv`
- `node_modules`
- `__pycache__`
- `.idea`

## Important limitation

No local model can safely keep a whole medium/large project literally loaded in active context forever. Continue and Ollama still operate with context limits, so the correct design is:

- keep a project snapshot
- keep rules
- inspect exact files when needed
- refresh after changes

That is why this system behaves like "project awareness" rather than fake infinite memory.

## Suggested workflow for you

1. Open the project in VS Code or PyCharm.
2. Open Continue.
3. Say `initialize this project`.
4. Work normally.
5. After manual code edits, say `read the project again to be aligned with the current state of the code`.
6. For debugging, ask concrete questions about routes, templates, or features.

## Example prompts

### Understand architecture

```text
initialize this project and explain the architecture like I am the maintainer
```

### Re-sync after edits

```text
read the project again to be aligned with the current state of the code
```

### Investigate a route bug

```text
why does post("/my-stories") break? investigate and find out using the current files only
```

### Add a feature

```text
initialize this project, inspect the current create and edit flow, then propose how to add draft saving without breaking the current structure
```

## Why this setup is the best fit here

For your use case, this is stronger than just opening Continue with a local model and hoping the workspace context is enough. The MCP layer gives the model explicit tools to:

- initialize the project deliberately
- refresh deliberately
- search deliberately
- inspect exact files deliberately

That is the closest local equivalent to the agent-style workflow you described.
