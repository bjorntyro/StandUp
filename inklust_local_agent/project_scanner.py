from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

TEXT_EXTENSIONS = {
    ".py", ".html", ".jinja", ".j2", ".css", ".js", ".ts", ".json", ".toml",
    ".ini", ".cfg", ".env", ".txt", ".md", ".sql", ".yml", ".yaml", ".xml",
    ".gitignore", ".dockerfile", ".sh", ".ps1",
}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg", ".woff", ".woff2",
    ".ttf", ".eot", ".pdf", ".zip", ".db", ".sqlite", ".sqlite3", ".pyc",
}

EXCLUDED_DIRS = {
    ".git", ".idea", ".vscode", ".venv", "venv", "env", "__pycache__", "node_modules",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".next", "dist", "build", ".ai",
}

KEY_FILES = [
    "backend/main.py",
    "backend/config.py",
    "backend/db/database.py",
    "backend/storage.py",
    "frontend/templates/base.html",
    "requirements.txt",
    "pyproject.toml",
    "alembic.ini",
]

ROUTE_PATTERN = re.compile(r"@(\w+)\.(get|post|put|delete|patch)\(\s*[\"\']([^\"\']+)[\"\']")
FUNC_PATTERN = re.compile(r"^def\s+(\w+)\(", re.MULTILINE)
CLASS_PATTERN = re.compile(r"^class\s+(\w+)\b", re.MULTILINE)
IMPORT_PATTERN = re.compile(r"^(?:from\s+([\w\.]+)\s+import|import\s+([\w\.]+))", re.MULTILINE)


@dataclass
class FileRecord:
    path: str
    size: int
    sha1: str
    category: str
    functions: list[str]
    classes: list[str]
    routes: list[str]
    imports: list[str]


def _is_text_file(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in BINARY_EXTENSIONS:
        return False
    if suffix in TEXT_EXTENSIONS:
        return True
    if path.name.startswith(".") and suffix == "":
        return True
    return False


def _should_skip(path: Path, root: Path) -> bool:
    rel_parts = path.relative_to(root).parts
    return any(part in EXCLUDED_DIRS for part in rel_parts)


def _read_text_safe(path: Path, max_bytes: int = 2_000_000) -> str:
    data = path.read_bytes()[:max_bytes]
    for encoding in ("utf-8", "utf-8-sig", "utf-16", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _file_category(rel_path: str) -> str:
    path = rel_path.replace("\\", "/")
    if path.startswith("backend/"):
        return "backend"
    if path.startswith("frontend/templates/"):
        return "templates"
    if path.startswith("frontend/static/"):
        return "static"
    if path.startswith("alembic/"):
        return "migrations"
    if path.startswith(".continue/"):
        return "continue"
    return "other"


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def _summarize_python(text: str) -> tuple[list[str], list[str], list[str], list[str]]:
    functions = FUNC_PATTERN.findall(text)[:40]
    classes = CLASS_PATTERN.findall(text)[:20]
    routes = [f"{method.upper()} {route}" for _, method, route in ROUTE_PATTERN.findall(text)][:40]
    imports = []
    for left, right in IMPORT_PATTERN.findall(text):
        value = left or right
        if value:
            imports.append(value)
    deduped_imports = list(dict.fromkeys(imports))[:40]
    return functions, classes, routes, deduped_imports


def scan_project(root_path: str | Path) -> dict:
    root = Path(root_path).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Project root does not exist: {root}")

    records: list[FileRecord] = []
    tree_lines: list[str] = []
    route_index: list[dict] = []
    template_files: list[str] = []
    static_assets: list[str] = []
    key_file_contents: dict[str, str] = {}

    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if _should_skip(path, root):
            continue

        rel = path.relative_to(root).as_posix()
        if len(rel.split("/")) <= 6:
            tree_lines.append(rel)

        if not _is_text_file(path):
            if rel.startswith("frontend/static/"):
                static_assets.append(rel)
            continue

        data = path.read_bytes()
        text = _read_text_safe(path)
        category = _file_category(rel)
        functions: list[str] = []
        classes: list[str] = []
        routes: list[str] = []
        imports: list[str] = []

        if path.suffix.lower() == ".py":
            functions, classes, routes, imports = _summarize_python(text)
            for route in routes:
                route_index.append({"path": rel, "route": route})

        if rel.startswith("frontend/templates/"):
            template_files.append(rel)

        if rel in KEY_FILES:
            key_file_contents[rel] = text[:12000]

        records.append(
            FileRecord(
                path=rel,
                size=len(data),
                sha1=_hash_bytes(data),
                category=category,
                functions=functions,
                classes=classes,
                routes=routes,
                imports=imports,
            )
        )

    summary = {
        "project_root": str(root),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(records),
        "template_count": len(template_files),
        "static_asset_count": len(static_assets),
        "backend_file_count": sum(1 for r in records if r.category == "backend"),
        "template_files": template_files[:100],
        "routes": route_index[:200],
        "key_files": key_file_contents,
        "file_records": [asdict(record) for record in records],
        "tree_preview": tree_lines[:400],
        "stack": detect_stack(root, records),
    }
    return summary


def detect_stack(root: Path, records: Iterable[FileRecord]) -> dict:
    paths = {record.path for record in records}
    stack = {
        "fastapi": "backend/main.py" in paths,
        "jinja2": any(path.startswith("frontend/templates/") for path in paths),
        "uvicorn": False,
        "sqlite_hint": False,
        "alembic": any(path.startswith("alembic/") for path in paths),
    }

    requirements_path = root / "requirements.txt"
    if requirements_path.exists():
        text = _read_text_safe(requirements_path, 200_000).lower()
        stack["uvicorn"] = "uvicorn" in text
        stack["sqlite_hint"] = "sqlite" in text or "sqlalchemy" in text
    return stack


def write_snapshot(root_path: str | Path) -> dict:
    root = Path(root_path).resolve()
    summary = scan_project(root)

    ai_dir = root / ".ai"
    ai_dir.mkdir(exist_ok=True)

    snapshot_path = ai_dir / "project_snapshot.json"
    summary_path = ai_dir / "project_context.md"
    tree_path = ai_dir / "file_tree.txt"
    log_path = ai_dir / "session_log.md"

    snapshot_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    tree_path.write_text("\n".join(summary["tree_preview"]), encoding="utf-8")
    summary_path.write_text(render_context_markdown(summary), encoding="utf-8")

    if not log_path.exists():
        log_path.write_text("# Session Log\n\n", encoding="utf-8")

    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"- {datetime.now().astimezone().isoformat()} | snapshot refreshed | {summary['file_count']} text files indexed\n")

    return summary


def render_context_markdown(summary: dict) -> str:
    lines = [
        "# Project Context",
        "",
        f"- Project root: `{summary['project_root']}`",
        f"- Snapshot generated: `{summary['generated_at']}`",
        f"- Indexed text files: `{summary['file_count']}`",
        f"- Template files: `{summary['template_count']}`",
        f"- Static assets skipped from deep indexing: `{summary['static_asset_count']}`",
        "",
        "## Detected stack",
        "",
    ]

    for key, value in summary["stack"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend([
        "",
        "## Routes",
        "",
    ])

    if summary["routes"]:
        for item in summary["routes"][:80]:
            lines.append(f"- `{item['route']}` in `{item['path']}`")
    else:
        lines.append("- No routes detected from Python decorators.")

    lines.extend([
        "",
        "## Key files",
        "",
    ])

    for path in summary["key_files"].keys():
        lines.append(f"- `{path}`")

    lines.extend([
        "",
        "## Tree preview",
        "",
        "```text",
        *summary["tree_preview"][:200],
        "```",
    ])

    return "\n".join(lines) + "\n"


def load_existing_snapshot(root_path: str | Path) -> dict | None:
    root = Path(root_path).resolve()
    snapshot_path = root / ".ai" / "project_snapshot.json"
    if not snapshot_path.exists():
        return None
    return json.loads(snapshot_path.read_text(encoding="utf-8"))


def find_files(root_path: str | Path, pattern: str, max_results: int = 50) -> list[str]:
    root = Path(root_path).resolve()
    results: list[str] = []
    lowered = pattern.lower()
    for path in sorted(root.rglob("*")):
        if path.is_dir() or _should_skip(path, root):
            continue
        rel = path.relative_to(root).as_posix()
        if lowered in rel.lower():
            results.append(rel)
        if len(results) >= max_results:
            break
    return results


def grep_project(root_path: str | Path, pattern: str, max_results: int = 50) -> list[dict]:
    root = Path(root_path).resolve()
    regex = re.compile(pattern, re.IGNORECASE)
    matches: list[dict] = []

    for path in sorted(root.rglob("*")):
        if path.is_dir() or _should_skip(path, root) or not _is_text_file(path):
            continue
        rel = path.relative_to(root).as_posix()
        text = _read_text_safe(path)
        for index, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                matches.append({"path": rel, "line": index, "text": line.strip()})
                if len(matches) >= max_results:
                    return matches
    return matches


def read_project_file(root_path: str | Path, relative_path: str, max_chars: int = 15000) -> str:
    path = Path(root_path).resolve() / relative_path
    if not path.exists():
        raise FileNotFoundError(f"File not found: {relative_path}")
    if not _is_text_file(path):
        raise ValueError(f"File is not a text file: {relative_path}")
    return _read_text_safe(path)[:max_chars]
