from __future__ import annotations

import argparse
import json
from pathlib import Path

from .project_scanner import find_files, grep_project, load_existing_snapshot, write_snapshot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="inklust-agent", description="InkLust local project agent utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create or refresh the local project snapshot")
    init_parser.add_argument("root", nargs="?", default=".")

    refresh_parser = subparsers.add_parser("refresh", help="Refresh the local project snapshot")
    refresh_parser.add_argument("root", nargs="?", default=".")

    status_parser = subparsers.add_parser("status", help="Print a short status summary")
    status_parser.add_argument("root", nargs="?", default=".")

    grep_parser = subparsers.add_parser("grep", help="Search the indexed project files")
    grep_parser.add_argument("pattern")
    grep_parser.add_argument("root", nargs="?", default=".")

    find_parser = subparsers.add_parser("find", help="Find files by name fragment")
    find_parser.add_argument("pattern")
    find_parser.add_argument("root", nargs="?", default=".")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command in {"init", "refresh"}:
        summary = write_snapshot(args.root)
        print(json.dumps({
            "project_root": summary["project_root"],
            "indexed_text_files": summary["file_count"],
            "routes": len(summary["routes"]),
            "snapshot": str(Path(summary["project_root"]) / ".ai" / "project_snapshot.json"),
        }, indent=2))
        return

    if args.command == "status":
        snapshot = load_existing_snapshot(args.root)
        if snapshot is None:
            raise SystemExit("No snapshot found. Run 'inklust-agent init' first.")
        print(json.dumps({
            "project_root": snapshot["project_root"],
            "generated_at": snapshot["generated_at"],
            "indexed_text_files": snapshot["file_count"],
            "routes": snapshot["routes"][:20],
        }, indent=2))
        return

    if args.command == "grep":
        print(json.dumps(grep_project(args.root, args.pattern), indent=2))
        return

    if args.command == "find":
        print(json.dumps(find_files(args.root, args.pattern), indent=2))
        return


if __name__ == "__main__":
    main()
