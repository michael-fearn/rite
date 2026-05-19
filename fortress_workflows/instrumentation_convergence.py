from __future__ import annotations

import sys
from pathlib import Path

from fortress_inventory.entity_graph import InventoryEntityGraph
from fortress_inventory.model import load_inventory_tree
from fortress_workflows.runner import CommandPhase, OperatorWorkflowPlan, WorkflowResult


OBSERVABILITY_SERVICE_NAME = "observability"


def build_instrumentation_convergence_plan(repo_root: Path) -> OperatorWorkflowPlan:
    model = load_inventory_tree(repo_root)
    if OBSERVABILITY_SERVICE_NAME not in model.services:
        raise ValueError(f"Service {OBSERVABILITY_SERVICE_NAME!r} is not declared")

    graph = InventoryEntityGraph(model)
    steps = [
        CommandPhase(
            id=f"vm-configure:{fact.vm_name}",
            display_name="VM Configure",
            command=[str(repo_root / "scripts" / "vm-configure"), fact.vm_name],
            diagnostic_label=f"VM Configure failed for VM {fact.vm_name}",
            streaming=True,
        )
        for fact in graph.instrumented_vm_facts()
    ]
    steps.append(
        CommandPhase(
            id="service-update:observability",
            display_name="Observability Service Update",
            command=[
                str(repo_root / "scripts" / "service-update"),
                OBSERVABILITY_SERVICE_NAME,
                "--auto-confirm",
            ],
            diagnostic_label="Observability Service Update failed",
            streaming=True,
        )
    )
    return OperatorWorkflowPlan(id="instrumentation-convergence", steps=steps)


def render_instrumentation_convergence_result(plan: OperatorWorkflowPlan, result: WorkflowResult) -> None:
    if result.success:
        return
    failed_phases = {phase.step_id: phase for phase in result.phase_results if phase.status == "failed"}
    for step in plan.steps:
        if isinstance(step, CommandPhase) and step.id in failed_phases:
            detail = failed_phases[step.id].failure_detail
            suffix = f": {detail}" if detail else ""
            print(f"{step.diagnostic_label}{suffix}", file=sys.stderr)
            return
