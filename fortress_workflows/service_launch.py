from __future__ import annotations

import sys
from pathlib import Path

from fortress_inventory.entity_graph import InventoryEntityGraph
from fortress_inventory.model import load_inventory_tree
from fortress_workflows.runner import CommandPhase, OperatorWorkflowPlan, WorkflowResult


def build_service_launch_plan(repo_root: Path, service: str, auto_confirm: bool = False) -> OperatorWorkflowPlan:
    model = load_inventory_tree(repo_root)
    intent = InventoryEntityGraph(model).service_launch_intent(service)
    if intent is None:
        raise ValueError(f"Service {service!r} is not declared")

    vm_lifecycle_command = [str(repo_root / "scripts" / "vm-up"), intent.backend_vm_name]
    if auto_confirm:
        vm_lifecycle_command.append("--auto-confirm")

    steps = [
        CommandPhase(
            id="vm-lifecycle",
            display_name="VM Lifecycle Convergence",
            command=vm_lifecycle_command,
            diagnostic_label=f"VM Lifecycle Convergence failed for Service {service}",
            streaming=True,
        ),
        CommandPhase(
            id="service-deploy",
            display_name="Service Deploy",
            command=[str(repo_root / "scripts" / "service-deploy"), service],
            diagnostic_label=f"Service Deploy failed for Service {service}",
            streaming=True,
        ),
    ]
    if service_declares_application_instrumentation(model.services[service]):
        steps.append(
            CommandPhase(
                id="observability-refresh",
                display_name="Observability Refresh",
                command=[str(repo_root / "scripts" / "service-update"), "observability", "--auto-confirm"],
                diagnostic_label=f"Observability Refresh failed after Service Launch {service}",
                streaming=True,
            )
        )
    if intent.requires_ingress_regeneration:
        steps.append(
            CommandPhase(
                id="ingress-regeneration",
                display_name="Ingress Regeneration",
                command=[str(repo_root / "scripts" / "ingress-regenerate")],
                diagnostic_label=f"Ingress Regeneration failed for Service {service}",
                streaming=True,
            )
        )

    return OperatorWorkflowPlan(id=f"service-launch:{service}", steps=steps)


def service_declares_application_instrumentation(service: dict) -> bool:
    return bool((service.get("instrumentation") or {}).get("telemetry_targets"))


def render_service_launch_result(plan: OperatorWorkflowPlan, result: WorkflowResult) -> None:
    if result.success:
        return
    failed_phases = {phase.step_id: phase for phase in result.phase_results if phase.status == "failed"}
    for step in plan.steps:
        if isinstance(step, CommandPhase) and step.id in failed_phases:
            detail = failed_phases[step.id].failure_detail
            suffix = f": {detail}" if detail else ""
            print(f"{step.diagnostic_label}{suffix}", file=sys.stderr)
            return
