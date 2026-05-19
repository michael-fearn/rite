"""Operator workflow execution primitives."""

from fortress_workflows.runner import (
    CommandPhase,
    ConfirmationGate,
    FailurePolicy,
    GateResult,
    OperatorWorkflowPlan,
    OperatorWorkflowRunner,
    PhaseResult,
    WorkflowResult,
)
from fortress_workflows.host_update import build_host_update_plan
from fortress_workflows.instrumentation_convergence import build_instrumentation_convergence_plan
from fortress_workflows.service_group_launch import build_service_group_launch_plan
from fortress_workflows.service_launch import build_service_launch_plan, render_service_launch_result
from fortress_workflows.service_update import build_service_update_plan, render_service_update_result
from fortress_workflows.template_update import build_template_update_plan
from fortress_workflows.vm_lifecycle import build_vm_lifecycle_plan, selected_vm_target_args
from fortress_workflows.vm_update import build_vm_update_plan

__all__ = [
    "build_host_update_plan",
    "build_instrumentation_convergence_plan",
    "build_service_group_launch_plan",
    "build_service_launch_plan",
    "build_service_update_plan",
    "build_template_update_plan",
    "build_vm_lifecycle_plan",
    "build_vm_update_plan",
    "CommandPhase",
    "ConfirmationGate",
    "FailurePolicy",
    "GateResult",
    "OperatorWorkflowPlan",
    "OperatorWorkflowRunner",
    "PhaseResult",
    "render_service_launch_result",
    "render_service_update_result",
    "selected_vm_target_args",
    "WorkflowResult",
]
