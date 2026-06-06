from __future__ import annotations

import os
from pathlib import Path

from fastmcp import FastMCP

from .project_scanner import (
    find_files,
    grep_project,
    load_existing_snapshot,
    read_project_file,
    render_context_markdown,
    write_snapshot,
)

SERVER_NAME = "InkLust Local Project Agent"
mcp = FastMCP(SERVER_NAME)


def _resolve_root(project_root: str | None = None) -> Path:
    candidate = project_root or os.environ.get("INKLUST_PROJECT_ROOT") or os.getcwd()
    return Path(candidate).resolve()


@mcp.tool
def init_project(project_root: str | None = None) -> dict:
    """Initialize the current workspace and create a fresh .ai snapshot for the whole project."""
    root = _resolve_root(project_root)
    summary = write_snapshot(root)
    return {
        "project_root": summary["project_root"],
        "generated_at": summary["generated_at"],
        "indexed_text_files": summary["file_count"],
        "detected_stack": summary["stack"],
        "routes_detected": len(summary["routes"]),
        "next_step": "Use get_project_briefing, read_project_file, grep_project, or list_project_files to investigate the codebase.",
    }


@mcp.tool
def refresh_project(project_root: str | None = None) -> dict:
    """Re-read the repository and refresh the local snapshot after code changes."""
    root = _resolve_root(project_root)
    summary = write_snapshot(root)
    return {
        "project_root": summary["project_root"],
        "generated_at": summary["generated_at"],
        "indexed_text_files": summary["file_count"],
        "routes_detected": len(summary["routes"]),
        "message": "Project snapshot refreshed successfully.",
    }


@mcp.tool
def get_project_briefing(project_root: str | None = None) -> str:
    """Return the current project briefing from the saved .ai snapshot."""
    root = _resolve_root(project_root)
    snapshot = load_existing_snapshot(root)
    if snapshot is None:
        snapshot = write_snapshot(root)
    return render_context_markdown(snapshot)


@mcp.tool
def list_project_files(project_root: str | None = None, category: str | None = None, max_files: int = 250) -> list[str]:
    """List indexed project files, optionally filtered by category such as backend, templates, static, migrations, continue, or other."""
    root = _resolve_root(project_root)
    snapshot = load_existing_snapshot(root)
    if snapshot is None:
        snapshot = write_snapshot(root)
    records = snapshot["file_records"]
    if category:
        records = [record for record in records if record["category"] == category]
    return [record["path"] for record in records[:max_files]]


@mcp.tool
def inspect_routes(project_root: str | None = None) -> list[dict]:
    """Return the detected FastAPI route list from the latest snapshot."""
    root = _resolve_root(project_root)
    snapshot = load_existing_snapshot(root)
    if snapshot is None:
        snapshot = write_snapshot(root)
    return snapshot["routes"]


@mcp.tool
def read_project_file_tool(relative_path: str, project_root: str | None = None, max_chars: int = 15000) -> dict:
    """Read the content of a text file inside the project."""
    root = _resolve_root(project_root)
    content = read_project_file(root, relative_path, max_chars=max_chars)
    return {"path": relative_path, "content": content}


@mcp.tool
def grep_project_tool(pattern: str, project_root: str | None = None, max_results: int = 50) -> list[dict]:
    """Search the project with a regular expression and return matching lines."""
    root = _resolve_root(project_root)
    return grep_project(root, pattern, max_results=max_results)


@mcp.tool
def find_files_tool(pattern: str, project_root: str | None = None, max_results: int = 50) -> list[str]:
    """Find files whose relative path contains the given text fragment."""
    root = _resolve_root(project_root)
    return find_files(root, pattern, max_results=max_results)


def main() -> None:
    mcp.run(transport="stdio", show_banner=False, log_level="ERROR")


if __name__ == "__main__":
    main()
