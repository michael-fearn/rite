from __future__ import annotations

from pathlib import Path

from fortress_inventory.entity_graph import InventoryEntityGraph
from fortress_inventory.model import load_inventory_tree
from fortress_workflows.runner import CommandPhase, OperatorWorkflowPlan
from fortress_workflows.service_launch import service_declares_application_instrumentation


def build_service_group_launch_plan(
    repo_root: Path,
    service_group: str,
    auto_confirm: bool = False,
) -> OperatorWorkflowPlan:
    model = load_inventory_tree(repo_root)
    intent = InventoryEntityGraph(model).service_group_launch_intent(service_group)

    vm_lifecycle_command = [str(repo_root / "scripts" / "vm-up"), intent.backend_vm_name]
    if auto_confirm:
        vm_lifecycle_command.append("--auto-confirm")

    steps = [
        CommandPhase(
            id="vm-lifecycle",
            display_name="VM Lifecycle Convergence",
            command=vm_lifecycle_command,
            diagnostic_label=f"VM Lifecycle Convergence failed for Service Group Launch {service_group}",
            streaming=True,
        ),
    ]
    for service_name in intent.service_names:
        steps.append(
            CommandPhase(
                id=f"service-deploy:{service_name}",
                display_name="Service Deploy",
                command=[str(repo_root / "scripts" / "service-deploy"), service_name],
                diagnostic_label=(
                    f"Service Deploy failed for Service {service_name} "
                    f"in Service Group Launch {service_group}"
                ),
                streaming=True,
            )
        )
    if any(
        service_declares_application_instrumentation(model.services[service_name])
        for service_name in intent.service_names
    ):
        steps.append(
            CommandPhase(
                id="observability-refresh",
                display_name="Observability Refresh",
                command=[str(repo_root / "scripts" / "service-update"), "observability", "--auto-confirm"],
                diagnostic_label=f"Observability Refresh failed after Service Group Launch {service_group}",
                streaming=True,
            )
        )
    if intent.requires_ingress_regeneration:
        steps.append(
            CommandPhase(
                id="ingress-regeneration",
                display_name="Ingress Regeneration",
                command=[str(repo_root / "scripts" / "ingress-regenerate")],
                diagnostic_label=f"Ingress Regeneration failed for Service Group Launch {service_group}",
                streaming=True,
            )
        )

    return OperatorWorkflowPlan(
        id=f"service-group-launch:{service_group}",
        steps=steps,
    )
