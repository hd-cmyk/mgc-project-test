from __future__ import annotations

import copy
import io
import json
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .graph import run_graph
from .llm_gateway import LLMGatewayConfig
from .planner import build_execution_plan
from .schemas import ProjectInput

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"
EXAMPLE_PATH = REPO_ROOT / "examples" / "python_bug" / "project_auto_fix.json"
RUNS: dict[str, dict[str, Any]] = {}
RUNS_LOCK = threading.Lock()
EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tcr-web")


def health_data() -> dict[str, Any]:
    config = LLMGatewayConfig.from_env()
    return {
        "status": "ok",
        "service": "TCR Agent Web",
        "llm_configured": bool(config.base_url and config.api_key and config.default_model),
    }


def example_data() -> dict[str, Any]:
    return json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))


def create_task(payload: dict[str, Any]) -> dict[str, Any]:
    project = normalize_project(payload)
    ProjectInput.from_dict(project)
    task_id = uuid.uuid4().hex
    task = {
        "task_id": task_id,
        "status": "pending",
        "created_at": time.time(),
        "started_at": None,
        "finished_at": None,
        "duration_ms": 0,
        "execution_plan": None,
        "node_states": initial_node_states(),
        "result": None,
        "error": "",
    }
    with RUNS_LOCK:
        RUNS[task_id] = task
    EXECUTOR.submit(execute_run, task_id, project)
    return {"task_id": task_id, "status": "pending"}


def get_task(task_id: str) -> dict[str, Any] | None:
    with RUNS_LOCK:
        task = RUNS.get(task_id)
        return copy.deepcopy(task) if task else None


def export_task(task_id: str) -> tuple[bytes, str] | None:
    """Build a zip containing the final workspace files for a completed run."""
    task = get_task(task_id)
    if not task or task.get("status") not in {"completed", "failed"}:
        return None
    result = task.get("result") or {}
    workspace_value = result.get("test_result", {}).get("workspace_dir", "")
    workspace = Path(workspace_value) if workspace_value else None
    project_files = result.get("project", {}).get("files", [])
    if workspace is None or not workspace.is_dir() or not project_files:
        return None

    buffer = io.BytesIO()
    exported_count = 0
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in project_files:
            relative = Path(str(item.get("path", "")))
            if not relative.parts or relative.is_absolute() or ".." in relative.parts:
                continue
            source = (workspace / relative).resolve()
            try:
                source.relative_to(workspace.resolve())
            except ValueError:
                continue
            if source.is_file():
                archive.write(source, relative.as_posix())
                exported_count += 1
    if exported_count == 0:
        return None
    run_id = str(result.get("run_id") or task_id)[:64]
    safe_run_id = "".join(char if char.isalnum() or char in "-_" else "_" for char in run_id)
    return buffer.getvalue(), f"{safe_run_id}_modified.zip"


def normalize_project(payload: dict[str, Any]) -> dict[str, Any]:
    project = copy.deepcopy(payload.get("project", payload))
    project.setdefault("run_id", f"web_{int(time.time() * 1000)}")
    project.setdefault("language", "python")
    project.setdefault("config", {})
    config = project["config"]
    config.setdefault("lint_tools", ["py_compile"])
    config.setdefault("test_timeout_seconds", 30)
    config.setdefault("ai_code_review_enabled", False)
    config.setdefault("report_use_llm", False)
    config.setdefault("auto_fix", True)
    config.setdefault("max_fix_rounds", 2)
    return project


def initial_node_states() -> dict[str, dict[str, str]]:
    return {
        "planner": {"status": "pending", "label": "规划"},
        "test_agent": {"status": "pending", "label": "TestAgent"},
        "report_agent": {"status": "pending", "label": "ReportAgent"},
        "fix_agent": {"status": "pending", "label": "FixAgent"},
        "verify_agent": {"status": "pending", "label": "VerifyAgent"},
        "complete": {"status": "pending", "label": "闭环完成"},
    }


def execute_run(task_id: str, project: dict[str, Any]) -> None:
    started = time.time()
    update_task(task_id, status="running", started_at=started)
    set_node(task_id, "planner", "running")
    try:
        update_task(task_id, execution_plan=build_execution_plan(project))
        set_node(task_id, "planner", "completed")
        set_node(task_id, "test_agent", "running")

        def on_node_complete(node: str, state: dict[str, Any]) -> None:
            result_key = {"test_agent": "test_result", "report_agent": "report_result", "fix_agent": "fix_result", "verify_agent": "verify_result"}.get(node)
            result_status = state.get(result_key, {}).get("status", "completed") if result_key else "completed"
            set_node(task_id, node, normalize_node_status(result_status))
            if node == "test_agent":
                set_node(task_id, "report_agent", "running")
            elif node == "report_agent":
                should_fix = state.get("report_result", {}).get("should_fix", False)
                if project["config"].get("auto_fix") and should_fix:
                    set_node(task_id, "fix_agent", "running")
                else:
                    set_node(task_id, "fix_agent", "skipped")
                    set_node(task_id, "verify_agent", "skipped")
            elif node == "fix_agent":
                set_node(task_id, "verify_agent", "running" if state.get("fix_result", {}).get("status") == "completed" else "skipped")

        result = run_graph(project, on_node_complete=on_node_complete)
        if "fix_result" not in result:
            set_node(task_id, "fix_agent", "skipped")
        if "verify_result" not in result:
            set_node(task_id, "verify_agent", "skipped")
        final_status = "completed" if not result.get("errors") else "failed"
        set_node(task_id, "complete", final_status)
        update_task(task_id, status=final_status, result=result, finished_at=time.time(), duration_ms=int((time.time() - started) * 1000))
    except Exception as exc:
        set_node(task_id, "complete", "failed")
        update_task(task_id, status="failed", error=str(exc), finished_at=time.time(), duration_ms=int((time.time() - started) * 1000))


def normalize_node_status(status: str) -> str:
    if status in {"passed", "completed"}:
        return "completed"
    return status if status in {"failed", "skipped"} else "completed"


def update_task(task_id: str, **values: Any) -> None:
    with RUNS_LOCK:
        RUNS[task_id].update(values)


def set_node(task_id: str, node: str, status: str) -> None:
    with RUNS_LOCK:
        RUNS[task_id]["node_states"][node]["status"] = status
