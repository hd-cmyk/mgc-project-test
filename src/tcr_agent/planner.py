from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .schemas import ProjectInput
from .tools import resolve_test_command


def build_execution_plan(project: ProjectInput | dict[str, Any]) -> dict[str, Any]:
    project_input = project if isinstance(project, ProjectInput) else ProjectInput.from_dict(project)
    source_files = [item.path for item in project_input.files if not is_test_file(item.path)]
    test_files = [item.path for item in project_input.files if is_test_file(item.path)]
    command = resolve_test_command(project_input)
    framework = "pytest" if "pytest" in command else "unittest" if "unittest" in command else "py_compile"
    checks = ["unit_test", *[str(item) for item in project_input.config.get("lint_tools", ["py_compile"])]]
    if project_input.config.get("ai_code_review_enabled"):
        checks.append("ai_code_review")
    return {
        "language": project_input.language,
        "source_files": source_files,
        "test_files": test_files,
        "test_framework": framework,
        "test_command": display_command(command),
        "checks": checks,
        "auto_fix_enabled": bool(project_input.config.get("auto_fix", False)),
        "max_fix_rounds": int(project_input.config.get("max_fix_rounds", 2)),
        "steps": [
            {"id": "test", "name": "执行自动化测试", "executor": "TestAgent", "status": "pending"},
            {"id": "analyze", "name": "分析测试和代码问题", "executor": "ReportAgent", "status": "pending"},
            {
                "id": "fix",
                "name": "执行自主修复",
                "executor": "FixAgent",
                "condition": "auto_fix && should_fix",
                "status": "pending",
            },
            {
                "id": "verify",
                "name": "执行回归验证",
                "executor": "VerifyAgent",
                "condition": "fix_completed",
                "status": "pending",
            },
        ],
    }


def is_test_file(path: str) -> bool:
    name = Path(path).name
    return name.startswith("test_") or name.endswith("_test.py")


def display_command(command: list[str]) -> str:
    displayed = ["python" if item == sys.executable else item for item in command]
    return " ".join(displayed)
