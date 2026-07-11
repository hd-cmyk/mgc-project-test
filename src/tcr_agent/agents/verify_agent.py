from __future__ import annotations

from pathlib import Path

from ..schemas import GraphState, ProjectInput, Status, VerifyAgentResult
from ..tools import run_python_compliance, run_python_tests


def run_verify_agent(state: GraphState) -> GraphState:
    try:
        project = ProjectInput.from_dict(state["project"])
        workspace = Path(state.get("test_result", {}).get("workspace_dir", ""))
        if not workspace.is_dir():
            raise ValueError("TestAgent workspace is missing")
        test_result = run_python_tests(project, workspace)
        compliance_results = run_python_compliance(project, workspace)
        passed = test_result.status == Status.PASSED and all(
            item.status != Status.FAILED for item in compliance_results
        )
        result = VerifyAgentResult(
            agent="VerifyAgent",
            status=Status.PASSED if passed else Status.FAILED,
            test_results=[test_result],
            compliance_results=compliance_results,
            passed=passed,
        )
        return {**state, "verify_result": result.to_dict()}
    except Exception as exc:
        errors = [*state.get("errors", []), f"VerifyAgent failed: {exc}"]
        result = VerifyAgentResult(
            agent="VerifyAgent",
            status=Status.FAILED,
            test_results=[],
            compliance_results=[],
            passed=False,
        )
        return {**state, "errors": errors, "verify_result": result.to_dict()}
