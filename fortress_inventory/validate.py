from .model import load_inventory_tree
from .service_runtime_intent import analyze_service_runtime_intent
from .validation.acceptance import validate_acceptance_policy_host_coverage
from .validation.datasets import (
    validate_dataset_lifecycle_policy,
    validate_dataset_names,
    validate_dataset_nas_refs,
)
from .validation.errors import ValidationError
from .validation.hosts import (
    validate_host_ingress_routes,
    validate_host_proxmox_endpoints,
    validate_vm_host_resources,
)
from .validation.services import (
    validate_ingress_dns_targets,
    validate_native_services,
    validate_quadlet_services,
    validate_service_backends,
    validate_service_hostnames,
    validate_service_ingress_contract,
    validate_service_share_backed_volumes,
)
from .validation.vms import (
    validate_vm_launchable_service_groups,
    validate_vm_inventory_policy,
    validate_vm_mounts,
    validate_vm_refs,
)


def validate_inventory_tree(root, allow_ephemeral_datasets=False):
    return validate_inventory_model(
        load_inventory_tree(root),
        allow_ephemeral_datasets=allow_ephemeral_datasets,
    )


def validate_inventory_model(model, allow_ephemeral_datasets=False):
    errors = []
    service_runtime_intent = analyze_service_runtime_intent(model)
    errors.extend(validate_service_backends(model, runtime_intent=service_runtime_intent))
    errors.extend(validate_service_ingress_contract(model))
    errors.extend(validate_ingress_dns_targets(model))
    errors.extend(validate_service_hostnames(model))
    errors.extend(validate_host_proxmox_endpoints(model))
    errors.extend(validate_host_ingress_routes(model))
    errors.extend(validate_quadlet_services(model, runtime_intent=service_runtime_intent))
    errors.extend(validate_native_services(model, runtime_intent=service_runtime_intent))
    errors.extend(validate_service_share_backed_volumes(model, runtime_intent=service_runtime_intent))
    errors.extend(validate_vm_inventory_policy(model))
    errors.extend(validate_vm_refs(model))
    errors.extend(validate_vm_launchable_service_groups(model))
    errors.extend(validate_dataset_names(model))
    errors.extend(validate_dataset_nas_refs(model))
    errors.extend(
        validate_dataset_lifecycle_policy(
            model,
            allow_ephemeral_datasets=allow_ephemeral_datasets,
        )
    )
    errors.extend(validate_acceptance_policy_host_coverage(model))
    errors.extend(validate_vm_mounts(model))
    errors.extend(validate_vm_host_resources(model))
    return errors
