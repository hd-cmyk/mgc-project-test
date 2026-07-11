from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .planner import build_execution_plan
from .schemas import ProjectInput
from .web_runtime import STATIC_DIR, create_task, example_data, export_task, get_task, health_data, normalize_project

app = FastAPI(title="TCR 自动化测试智能体", version="0.2.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return health_data()


@app.get("/api/example")
def example() -> dict[str, Any]:
    return example_data()


@app.post("/api/plan")
def plan(payload: dict[str, Any]) -> dict[str, Any]:
    project = ProjectInput.from_dict(normalize_project(payload))
    return {"execution_plan": build_execution_plan(project)}


@app.post("/api/runs", status_code=202)
def create_run(payload: dict[str, Any]) -> dict[str, Any]:
    return create_task(payload)


@app.get("/api/runs/{task_id}")
def get_run(task_id: str) -> dict[str, Any]:
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="run not found")
    return task


@app.get("/api/runs/{task_id}/export")
def export_run(task_id: str) -> Response:
    exported = export_task(task_id)
    if exported is None:
        raise HTTPException(status_code=404, detail="modified files are not available")
    content, filename = exported
    return Response(
        content=content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
