from __future__ import annotations

from typing import Any

from .agents.fix_agent import run_fix_agent
from .agents.report_agent import run_report_agent
from .agents.test_agent import run_test_agent
from .agents.verify_agent import run_verify_agent
from .schemas import GraphState, ProjectInput


def build_graph():
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise RuntimeError("LangGraph is not installed. Run `python3 -m pip install -e .`.") from exc

    graph = StateGraph(GraphState)
    graph.add_node("test_agent", run_test_agent)
    graph.add_node("report_agent", run_report_agent)
    graph.add_node("fix_agent", run_fix_agent)
    graph.add_node("verify_agent", run_verify_agent)
    graph.add_edge(START, "test_agent")
    graph.add_edge("test_agent", "report_agent")
    graph.add_conditional_edges("report_agent", route_after_report, {"fix": "fix_agent", "end": END})
    graph.add_conditional_edges("fix_agent", route_after_fix, {"verify": "verify_agent", "end": END})
    graph.add_edge("verify_agent", END)
    return graph.compile()


def run_graph(project: ProjectInput | dict[str, Any]) -> GraphState:
    project_input = project if isinstance(project, ProjectInput) else ProjectInput.from_dict(project)
    app = build_graph()
    initial_state: GraphState = {
        "run_id": project_input.run_id,
        "project": project_input.to_dict(),
        "errors": [],
    }
    return app.invoke(initial_state)


def run_direct(project: ProjectInput | dict[str, Any]) -> GraphState:
    project_input = project if isinstance(project, ProjectInput) else ProjectInput.from_dict(project)
    initial_state: GraphState = {
        "run_id": project_input.run_id,
        "project": project_input.to_dict(),
        "errors": [],
    }
    state = run_test_agent(initial_state)
    state = run_report_agent(state)
    if route_after_report(state) == "end":
        return state
    state = run_fix_agent(state)
    if route_after_fix(state) == "end":
        return state
    return run_verify_agent(state)


def route_after_report(state: GraphState) -> str:
    config = state.get("project", {}).get("config", {})
    should_fix = bool(state.get("report_result", {}).get("should_fix"))
    return "fix" if bool(config.get("auto_fix")) and should_fix else "end"


def route_after_fix(state: GraphState) -> str:
    return "verify" if state.get("fix_result", {}).get("status") == "completed" else "end"
