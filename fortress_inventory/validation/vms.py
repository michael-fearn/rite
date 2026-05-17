from .errors import ValidationError


def validate_vm_inventory_policy(model):
    errors = []
    for vm_name, vm in model.vms.items():
        vmid = vm.get("vmid")
        lifecycle = vm.get("lifecycle", {})
        lifecycle_kind = lifecycle.get("kind", "ordinary")
        generated = lifecycle.get("generated") is True

        if vm_name.startswith("tmp-") and not generated:
            errors.append(
                ValidationError(
                    "reserved_tmp_vm_name",
                    f"inventory/vms/{vm_name}.yaml",
                    f"VM name {vm_name} uses reserved tmp- prefix for generated temporary VMs",
                )
            )

        if not isinstance(vmid, int):
            continue
        if 9000 <= vmid <= 9999:
            errors.append(
                ValidationError(
                    "vm_uses_template_vmid",
                    f"inventory/vms/{vm_name}.yaml.vmid",
                    f"VM {vm_name} uses VMID {vmid}, which is reserved for Templates",
                )
            )
        elif lifecycle_kind == "operational":
            if not 8900 <= vmid <= 8999:
                errors.append(
                    ValidationError(
                        "operational_vm_vmid_out_of_range",
                        f"inventory/vms/{vm_name}.yaml.vmid",
                        f"Operational VM {vm_name} uses VMID {vmid} outside 8900-8999",
                    )
                )
        elif 8900 <= vmid <= 8999:
            errors.append(
                ValidationError(
                    "ordinary_vm_operational_vmid",
                    f"inventory/vms/{vm_name}.yaml.vmid",
                    f"Ordinary VM {vm_name} uses VMID {vmid}, which is reserved for Operational VMs",
                )
            )
    return errors


def validate_vm_refs(model):
    errors = []
    for vm_name, vm in model.vms.items():
        host_name = vm.get("placement", {}).get("host")
        if host_name and host_name not in model.hosts:
            errors.append(
                ValidationError(
                    "missing_vm_host",
                    f"inventory/vms/{vm_name}.yaml.placement.host",
                    f"VM {vm_name} is placed on missing Host {host_name}",
                )
            )
        template_name = vm.get("source", {}).get("template")
        if template_name and template_name not in model.templates:
            errors.append(
                ValidationError(
                    "missing_vm_template",
                    f"inventory/vms/{vm_name}.yaml.source.template",
                    f"VM {vm_name} references missing Template {template_name}",
                )
            )
    return errors


def validate_vm_mounts(model):
    errors = []
    dataset_names = {dataset.get("name") for dataset in model.datasets.values() if dataset.get("name")}
    for vm_name, vm in model.vms.items():
        mounts = vm.get("mounts", []) or []
        if mounts and len(_vm_static_addresses(vm)) != 1:
            errors.append(
                ValidationError(
                    "ambiguous_vm_mount_client_address",
                    f"inventory/vms/{vm_name}.yaml.network.interfaces",
                    f"VM {vm_name} declares Mounts but does not have exactly one static IP address",
                )
            )

        seen_mount_names = {}
        for index, mount in enumerate(mounts):
            mount_name = mount.get("name")
            if mount_name:
                if mount_name in seen_mount_names:
                    errors.append(
                        ValidationError(
                            "duplicate_vm_mount_name",
                            f"inventory/vms/{vm_name}.yaml.mounts[{index}].name",
                            f"VM {vm_name} declares duplicate Mount Name {mount_name}",
                        )
                    )
                else:
                    seen_mount_names[mount_name] = index

            dataset_name = mount.get("dataset")
            if dataset_name and dataset_name not in dataset_names:
                errors.append(
                    ValidationError(
                        "missing_vm_mount_dataset",
                        f"inventory/vms/{vm_name}.yaml.mounts[{index}].dataset",
                        f"VM {vm_name} Mount {mount.get('name', index)} references missing Dataset {dataset_name}",
                    )
                )

            contradicting_option = _mount_access_contradicting_option(mount)
            if contradicting_option:
                errors.append(
                    ValidationError(
                        "vm_mount_access_option_conflict",
                        f"inventory/vms/{vm_name}.yaml.mounts[{index}].options_extra",
                        f"VM {vm_name} Mount {mount.get('name', index)} uses option {contradicting_option} "
                        f"which contradicts access {mount.get('access')}",
                    )
                )
    return errors


def validate_vm_launchable_service_groups(model):
    errors = []
    declaring_vms_by_group = {}
    for vm_name, vm in model.vms.items():
        for group_index, group in enumerate(vm.get("launchable_service_groups", []) or []):
            group_name = group.get("name")
            existing_vm_name = declaring_vms_by_group.setdefault(group_name, vm_name)
            if existing_vm_name != vm_name:
                errors.append(
                    ValidationError(
                        "duplicate_launchable_service_group",
                        f"inventory/vms/{vm_name}.yaml.launchable_service_groups[{group_index}].name",
                        f"Service Group {group_name} is declared launchable by both {existing_vm_name} and {vm_name}",
                    )
                )
            ordered_service_names = group.get("launch_order", []) or []
            seen_service_names = {}
            for service_index, service_name in enumerate(ordered_service_names):
                if service_name in seen_service_names:
                    errors.append(
                        ValidationError(
                            "duplicate_launch_order_service",
                            (
                                f"inventory/vms/{vm_name}.yaml."
                                f"launchable_service_groups[{group_index}].launch_order[{service_index}]"
                            ),
                            f"VM {vm_name} Launch Order declares duplicate Service {service_name}",
                        )
                    )
                else:
                    seen_service_names[service_name] = service_index

            for service_index, service_name in enumerate(group.get("launch_order", []) or []):
                if service_name not in model.services:
                    errors.append(
                        ValidationError(
                            "missing_launch_order_service",
                            (
                                f"inventory/vms/{vm_name}.yaml."
                                f"launchable_service_groups[{group_index}].launch_order[{service_index}]"
                            ),
                            f"VM {vm_name} Launch Order references missing Service {service_name}",
                        )
                    )
                    continue
                service = model.services[service_name]
                if service.get("service_group") != group_name:
                    errors.append(
                        ValidationError(
                            "launch_order_service_group_mismatch",
                            (
                                f"inventory/vms/{vm_name}.yaml."
                                f"launchable_service_groups[{group_index}].launch_order[{service_index}]"
                            ),
                            f"VM {vm_name} Launch Order includes Service {service_name}, "
                            f"which does not declare Service Group {group_name}",
                        )
                    )
                backend_vm_name = _service_backend_vm_name(service)
                if backend_vm_name != vm_name:
                    errors.append(
                        ValidationError(
                            "launch_order_service_backend_vm_mismatch",
                            (
                                f"inventory/vms/{vm_name}.yaml."
                                f"launchable_service_groups[{group_index}].launch_order[{service_index}]"
                            ),
                            f"VM {vm_name} Launch Order includes Service {service_name}, "
                            f"which uses Backend VM {backend_vm_name}",
                        )
                    )
            expected_service_names = {
                service_name
                for service_name, service in model.services.items()
                if service.get("service_group") == group_name and _service_backend_vm_name(service) == vm_name
            }
            missing_service_names = sorted(expected_service_names - set(ordered_service_names))
            for service_name in missing_service_names:
                errors.append(
                    ValidationError(
                        "missing_launch_order_service_group_member",
                        f"inventory/vms/{vm_name}.yaml.launchable_service_groups[{group_index}].launch_order",
                        f"VM {vm_name} Launch Order for Service Group {group_name} omits Service {service_name}",
                    )
                )
    return errors


def _service_backend_vm_name(service):
    backend = service.get("backend", {})
    if not isinstance(backend, dict):
        return None
    return backend.get("vm")


def _mount_access_contradicting_option(mount):
    access = mount.get("access")
    options = {str(option).split("=", 1)[0] for option in mount.get("options_extra", []) or []}
    if access == "read_only" and "rw" in options:
        return "rw"
    if access == "read_write" and "ro" in options:
        return "ro"
    return None


def _vm_static_addresses(vm):
    addresses = []
    for interface in vm.get("network", {}).get("interfaces", []) or []:
        address = interface.get("address")
        if address:
            addresses.append(address.split("/", 1)[0])
    return addresses
