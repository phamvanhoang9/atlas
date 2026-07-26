"""Tests that plan_gate and contradiction_check are wired into the compiled
LangGraph workflow (Giai đoạn 4)."""

from src.orchestration.workflow import build_workflow


def test_workflow_includes_deep_dive_nodes():
    workflow = build_workflow()
    nodes = set(workflow.get_graph().nodes.keys())
    assert "plan_gate" in nodes
    assert "contradiction_check" in nodes
