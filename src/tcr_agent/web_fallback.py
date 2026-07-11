from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .planner import build_execution_plan
from .schemas import ProjectInput
from .web_runtime import STATIC_DIR, create_task, example_data, export_task, get_task, health_data, normalize_project


class TCRRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            return self.send_json(health_data())
        if path == "/api/example":
            return self.send_json(example_data())
        if path.startswith("/api/runs/") and path.endswith("/export"):
            task_id = path.split("/")[-2]
            exported = export_task(task_id)
            if exported is None:
                return self.send_json({"detail": "modified files are not available"}, 404)
            body, filename = exported
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path.startswith("/api/runs/"):
            task = get_task(path.rsplit("/", 1)[-1])
            return self.send_json(task or {"detail": "run not found"}, 200 if task else 404)
        if path == "/":
            return self.send_file(STATIC_DIR / "index.html")
        if path.startswith("/static/"):
            return self.send_file(STATIC_DIR / path.removeprefix("/static/"))
        self.send_json({"detail": "not found"}, 404)

    def do_POST(self) -> None:
        try:
            payload = self.read_json()
            if self.path == "/api/plan":
                project = ProjectInput.from_dict(normalize_project(payload))
                return self.send_json({"execution_plan": build_execution_plan(project)})
            if self.path == "/api/runs":
                return self.send_json(create_task(payload), 202)
            self.send_json({"detail": "not found"}, 404)
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json({"detail": str(exc)}, 400)

    def read_json(self) -> dict:
        size = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(size).decode("utf-8"))

    def send_json(self, data: object, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path) -> None:
        try:
            resolved = path.resolve()
            resolved.relative_to(STATIC_DIR.resolve())
            body = resolved.read_bytes()
        except (FileNotFoundError, ValueError):
            return self.send_json({"detail": "not found"}, 404)
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(resolved.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[TCR Web] {format % args}")


def run_fallback(host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), TCRRequestHandler)
    print(f"TCR Web GUI running at http://{host}:{port} (stdlib fallback)")
    server.serve_forever()
