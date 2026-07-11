import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tcr_agent.agents.fix_agent import run_fix_agent
from tcr_agent.agents.verify_agent import run_verify_agent
from tcr_agent.graph import run_direct
from tcr_agent.schemas import CommandResult, Status
from tcr_agent.tools import parse_test_output


def demo_project(auto_fix=False):
    return {
        "run_id": "auto_fix_test",
        "language": "python",
        "files": [
            {"path": "main.py", "content": "def add(a, b):\n    return a - b\n"},
            {
                "path": "test_main.py",
                "content": (
                    "import unittest\nfrom main import add\n\n"
                    "class TestAdd(unittest.TestCase):\n"
                    "    def test_add(self):\n"
                    "        self.assertEqual(add(1, 2), 3)\n"
                ),
            },
        ],
        "config": {
            "lint_tools": ["py_compile"],
            "test_command": [sys.executable, "-m", "unittest", "discover", "-v"],
            "report_use_llm": False,
            "auto_fix": auto_fix,
        },
    }


class TestFailureParsing(unittest.TestCase):
    def test_pytest_failure_extracts_file_line_and_message(self):
        output = """============================= test session starts ==============================
collected 1 item

test_main.py F                                                           [100%]

=================================== FAILURES ===================================
___________________________________ test_add ___________________________________

    def test_add():
>       assert add(1, 2) == 3
E       assert -1 == 3

test_main.py:7: AssertionError
=========================== short test summary info ============================
FAILED test_main.py::test_add - assert -1 == 3
============================== 1 failed in 0.01s ===============================
"""
        result = CommandResult("run_tests", ["python", "-m", "pytest", "-q"], ".", Status.FAILED, 1, 1, stdout=output)
        summary = parse_test_output(result, result.command)

        self.assertEqual(summary.failures[0].file, "test_main.py")
        self.assertEqual(summary.failures[0].line, 7)
        self.assertIn("-1 == 3", summary.failures[0].message)

    def test_unittest_failure_extracts_test_id_file_line_and_message(self):
        output = """test_add (test_main.TestAdd.test_add) ... FAIL

======================================================================
FAIL: test_add (test_main.TestAdd.test_add)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/tmp/workspace/test_main.py", line 7, in test_add
    self.assertEqual(add(1, 2), 3)
AssertionError: -1 != 3

----------------------------------------------------------------------
Ran 1 test in 0.000s

FAILED (failures=1)
"""
        command = [sys.executable, "-m", "unittest", "discover", "-v"]
        result = CommandResult("run_tests", command, ".", Status.FAILED, 1, 1, stderr=output)
        failure = parse_test_output(result, command).failures[0]

        self.assertEqual(failure.test_id, "test_main.TestAdd.test_add")
        self.assertEqual(failure.file, "test_main.py")
        self.assertEqual(failure.line, 7)
        self.assertEqual(failure.message, "AssertionError: -1 != 3")


class TestAutoFixFlow(unittest.TestCase):
    def test_fix_agent_modifies_only_workspace_and_keeps_patch(self):
        state = run_direct(demo_project(auto_fix=False))
        original = demo_project()["files"][0]["content"]
        fixed = run_fix_agent(state)

        workspace_main = Path(state["test_result"]["workspace_dir"]) / "main.py"
        self.assertEqual(fixed["fix_result"]["status"], "completed")
        self.assertIn("return a + b", workspace_main.read_text(encoding="utf-8"))
        self.assertIn("-    return a - b", fixed["fix_result"]["patches"][0])
        self.assertIn("return a - b", original)

    def test_verify_agent_passes_after_fix(self):
        state = run_direct(demo_project(auto_fix=False))
        state = run_fix_agent(state)
        state = run_verify_agent(state)

        self.assertEqual(state["test_result"]["status"], "failed")
        self.assertEqual(state["verify_result"]["status"], "passed")
        self.assertTrue(state["verify_result"]["passed"])

    def test_auto_fix_false_preserves_old_flow(self):
        state = run_direct(demo_project(auto_fix=False))
        self.assertNotIn("fix_result", state)
        self.assertNotIn("verify_result", state)

    def test_auto_fix_true_runs_complete_loop(self):
        state = run_direct(demo_project(auto_fix=True))
        self.assertEqual(state["test_result"]["status"], "failed")
        self.assertTrue(state["report_result"]["should_fix"])
        self.assertEqual(state["fix_result"]["status"], "completed")
        self.assertEqual(state["verify_result"]["status"], "passed")
        self.assertTrue(state["verify_result"]["passed"])

    def test_example_auto_fix_project_runs(self):
        path = Path(__file__).resolve().parents[1] / "examples/python_bug/project_auto_fix.json"
        state = run_direct(json.loads(path.read_text(encoding="utf-8")))
        self.assertTrue(state["verify_result"]["passed"])


if __name__ == "__main__":
    unittest.main()
