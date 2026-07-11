import json
import io
import unittest
import zipfile
from pathlib import Path

from tcr_agent.planner import build_execution_plan
from tcr_agent.web_runtime import RUNS, RUNS_LOCK, execute_run, export_task, health_data, initial_node_states, normalize_project


ROOT = Path(__file__).resolve().parents[1]


def load_example():
    return json.loads((ROOT / "examples/python_bug/project_auto_fix.json").read_text(encoding="utf-8"))


class TestExecutionPlanner(unittest.TestCase):
    def test_builds_real_plan_from_project(self):
        plan = build_execution_plan(load_example())

        self.assertEqual(plan["language"], "python")
        self.assertEqual(plan["source_files"], ["main.py"])
        self.assertEqual(plan["test_files"], ["test_main.py"])
        self.assertIn(plan["test_framework"], {"pytest", "unittest"})
        self.assertTrue(plan["auto_fix_enabled"])
        self.assertEqual([step["executor"] for step in plan["steps"]], ["TestAgent", "ReportAgent", "FixAgent", "VerifyAgent"])


class TestWebTask(unittest.TestCase):
    def test_web_task_runs_real_self_healing_graph(self):
        task_id = "web_unit_test"
        with RUNS_LOCK:
            RUNS[task_id] = {
                "task_id": task_id,
                "status": "pending",
                "created_at": 0,
                "started_at": None,
                "finished_at": None,
                "duration_ms": 0,
                "execution_plan": None,
                "node_states": initial_node_states(),
                "result": None,
                "error": "",
            }

        execute_run(task_id, normalize_project(load_example()))
        task = RUNS.pop(task_id)

        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["node_states"]["planner"]["status"], "completed")
        self.assertEqual(task["node_states"]["verify_agent"]["status"], "completed")
        self.assertTrue(task["result"]["verify_result"]["passed"])
        self.assertGreater(task["duration_ms"], 0)

        with RUNS_LOCK:
            RUNS[task_id] = task
        exported = export_task(task_id)
        RUNS.pop(task_id)
        self.assertIsNotNone(exported)
        archive_bytes, filename = exported
        self.assertTrue(filename.endswith("_modified.zip"))
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            self.assertIn("main.py", archive.namelist())
            self.assertIn("return a + b", archive.read("main.py").decode("utf-8"))

    def test_health_exposes_boolean_not_credentials(self):
        result = health_data()
        self.assertIn("llm_configured", result)
        self.assertIsInstance(result["llm_configured"], bool)
        self.assertNotIn("api_key", result)


if __name__ == "__main__":
    unittest.main()
