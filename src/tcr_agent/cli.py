from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .graph import run_direct, run_graph


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the TCR agent prototype.")
    parser.add_argument("--input", help="Path to a project input JSON file.")
    parser.add_argument("--code", nargs="+", help="One or more Python source files to analyze.")
    parser.add_argument("--test", nargs="*", default=[], help="Optional Python test files to include.")
    parser.add_argument("--run-id", help="Run id. Defaults to a timestamped id.")
    parser.add_argument("--ai-review", action="store_true", help="Enable LLM code review.")
    parser.add_argument("--no-report-llm", action="store_true", help="Disable LLM report enhancement.")
    parser.add_argument("--auto-fix", action="store_true", help="Apply supported fixes and verify them in the temporary workspace.")
    parser.add_argument("--test-command", help="Override test command, for example: 'python -m unittest discover -v'.")
    parser.add_argument("--direct", action="store_true", help="Run TestAgent directly without LangGraph.")
    args = parser.parse_args()

    try:
        data = load_project_input(args)
        if args.auto_fix:
            data.setdefault("config", {})["auto_fix"] = True
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        state = run_direct(data) if args.direct else run_graph(data)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def load_project_input(args: argparse.Namespace) -> dict:
    if args.input:
        if args.code or args.test:
            raise ValueError("--input cannot be combined with --code or --test")
        return json.loads(Path(args.input).read_text(encoding="utf-8"))
    if not args.code:
        raise ValueError("Either --input or --code is required")
    return build_project_from_paths(args)


def build_project_from_paths(args: argparse.Namespace) -> dict:
    paths = [Path(item) for item in [*args.code, *args.test]]
    files = []
    for path in paths:
        if not path.exists():
            raise ValueError(f"file not found: {path}")
        if path.suffix != ".py":
            raise ValueError(f"only .py files are supported for --code/--test: {path}")
        files.append(
            {
                "path": path.name,
                "language": "python",
                "content": path.read_text(encoding="utf-8"),
            }
        )

    config = {
        "lint_tools": ["py_compile"],
        "test_timeout_seconds": 30,
        "ai_code_review_enabled": bool(args.ai_review),
        "report_use_llm": not args.no_report_llm,
        "auto_fix": bool(getattr(args, "auto_fix", False)),
        "max_fix_rounds": 2,
    }
    if args.test_command:
        config["test_command"] = args.test_command

    return {
        "run_id": args.run_id or f"local_py_{int(time.time())}",
        "language": "python",
        "files": files,
        "config": config,
    }


if __name__ == "__main__":
    raise SystemExit(main())
