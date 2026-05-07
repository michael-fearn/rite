from dataclasses import dataclass

from .model import load_inventory_tree


@dataclass(frozen=True)
class ValidationError:
    code: str
    path: str
    message: str


def validate_inventory_tree(root, allow_ephemeral_datasets=False):
    return validate_inventory_model(
        load_inventory_tree(root),
        allow_ephemeral_datasets=allow_ephemeral_datasets,
    )


def validate_inventory_model(model, allow_ephemeral_datasets=False):
    errors = []
    errors.extend(_validate_service_backends(model))
    errors.extend(_validate_service_hostnames(model))
    errors.extend(_validate_service_share_backed_volumes(model))
    errors.extend(_validate_vm_inventory_policy(model))
    errors.extend(_validate_vm_refs(model))
    errors.extend(_validate_dataset_names(model))
    errors.extend(_validate_dataset_nas_refs(model))
    errors.extend(_validate_dataset_lifecycle_policy(model, allow_ephemeral_datasets=allow_ephemeral_datasets))
    errors.extend(_validate_vm_mounts(model))
    errors.extend(_validate_vm_host_resources(model))
    return errors


def _validate_vm_inventory_policy(model):
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


def _validate_service_backends(model):
    errors = []
    seen_ports = {}
    for service_name, service in model.services.items():
        backend = service.get("backend", {})
        vm_name = backend.get("vm")
        port = backend.get("port")
        if vm_name and vm_name not in model.vms:
            errors.append(
                ValidationError(
                    "missing_service_backend_vm",
                    f"inventory/services/{service_name}.yaml.backend.vm",
                    f"Service {service_name} references missing Backend VM {vm_name}",
                )
            )
        if vm_name and port:
            key = (vm_name, port)
            if key in seen_ports:
                other_service = seen_ports[key]
                errors.append(
                    ValidationError(
                        "backend_port_collision",
                        f"inventory/services/{service_name}.yaml.backend.port",
                        f"Services {other_service} and {service_name} both use Backend {vm_name}:{port}",
                    )
                )
            else:
                seen_ports[key] = service_name
    return errors


def _validate_service_hostnames(model):
    errors = []
    seen = {}
    for service_name, service in model.services.items():
        hostname = service.get("hostname")
        if not hostname:
            continue
        if hostname in seen:
            errors.append(
                ValidationError(
                    "duplicate_service_hostname",
                    f"inventory/services/{service_name}.yaml.hostname",
                    f"Services {seen[hostname]} and {service_name} both publish hostname {hostname}",
                )
            )
        else:
            seen[hostname] = service_name
    return errors


def _validate_service_share_backed_volumes(model):
    errors = []
    for service_name, service in model.services.items():
        backend_vm_name = service.get("backend", {}).get("vm")
        backend_vm = model.vms.get(backend_vm_name)
        if not backend_vm:
            continue
        vm_mounts = {
            mount.get("name"): mount
            for mount in backend_vm.get("mounts", []) or []
            if mount.get("name")
        }
        for container_index, _container, volume_index, volume in _service_volumes(service):
            mount_name = volume.get("mount")
            if not mount_name:
                continue
            if _unsafe_share_backed_source(volume.get("source")):
                errors.append(
                    ValidationError(
                        "unsafe_service_volume_source",
                        _service_volume_path(service_name, container_index, volume_index, "source"),
                        f"Service {service_name} Share-backed Volume source {volume.get('source')} "
                        "must be / or a relative subpath without .. traversal",
                    )
                )
            if mount_name not in vm_mounts:
                errors.append(
                    ValidationError(
                        "missing_service_volume_mount",
                        _service_volume_path(service_name, container_index, volume_index, "mount"),
                        f"Service {service_name} Share-backed Volume references missing Mount Name {mount_name} "
                        f"on Backend VM {backend_vm_name}",
                    )
                )
                continue
            mount = vm_mounts[mount_name]
            volume_access = volume.get("access", mount.get("access"))
            if mount.get("access") == "read_only" and volume_access == "read_write":
                errors.append(
                    ValidationError(
                        "service_volume_widens_mount_access",
                        _service_volume_path(service_name, container_index, volume_index, "access"),
                        f"Service {service_name} Share-backed Volume requests read_write access to read_only "
                        f"Mount {mount_name} on Backend VM {backend_vm_name}",
                    )
                )
    return errors


def _unsafe_share_backed_source(source):
    if source == "/":
        return False
    if not source or source.startswith("/"):
        return True
    return ".." in str(source).split("/")


def _service_volumes(service):
    containers = service.get("deploy", {}).get("containers", []) or []
    for container_index, container in enumerate(containers):
        for volume_index, volume in enumerate(container.get("volumes", []) or []):
            yield container_index, container, volume_index, volume


def _service_volume_path(service_name, container_index, volume_index, field):
    return (
        f"inventory/services/{service_name}.yaml.deploy.containers"
        f"[{container_index}].volumes[{volume_index}].{field}"
    )


def _validate_vm_refs(model):
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


def _validate_dataset_names(model):
    errors = []
    seen = {}
    for dataset_file, dataset in model.datasets.items():
        dataset_name = dataset.get("name")
        if not dataset_name:
            continue
        if dataset_name in seen:
            errors.append(
                ValidationError(
                    "duplicate_dataset_name",
                    f"inventory/datasets/{dataset_file}.yaml.name",
                    f"Datasets {seen[dataset_name]} and {dataset_file} both declare name {dataset_name}",
                )
            )
        else:
            seen[dataset_name] = dataset_file
    return errors


def _validate_dataset_nas_refs(model):
    errors = []
    endpoints = set(model.nas_endpoints.keys())
    for dataset_file, dataset in model.datasets.items():
        nas_name = dataset.get("nas")
        if nas_name and nas_name not in endpoints:
            errors.append(
                ValidationError(
                    "missing_dataset_nas_endpoint",
                    f"inventory/datasets/{dataset_file}.yaml.nas",
                    f"Dataset {dataset.get('name', dataset_file)} references missing NAS endpoint {nas_name}",
                )
            )
    return errors


def _validate_dataset_lifecycle_policy(model, allow_ephemeral_datasets=False):
    errors = []
    if allow_ephemeral_datasets:
        return errors
    for dataset_file, dataset in model.datasets.items():
        if dataset.get("lifecycle") == "ephemeral":
            errors.append(
                ValidationError(
                    "ordinary_ephemeral_dataset",
                    f"inventory/datasets/{dataset_file}.yaml.lifecycle",
                    f"Dataset {dataset.get('name', dataset_file)} uses ephemeral lifecycle outside Acceptance Test inventory",
                )
            )
    return errors


def _validate_vm_mounts(model):
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


def _validate_vm_host_resources(model):
    errors = []
    for vm_name, vm in model.vms.items():
        host_name = vm.get("placement", {}).get("host")
        host = model.hosts.get(host_name)
        if not host:
            continue

        host_storage = {
            storage.get("name")
            for storage in host.get("hardware", {}).get("storage", []) or []
            if storage.get("name")
        }
        for index, disk in enumerate(vm.get("hardware", {}).get("disks", []) or []):
            storage_name = disk.get("storage")
            if storage_name and storage_name not in host_storage:
                errors.append(
                    ValidationError(
                        "missing_host_storage",
                        f"inventory/vms/{vm_name}.yaml.hardware.disks[{index}].storage",
                        f"VM {vm_name} uses storage {storage_name} not declared by Host {host_name}",
                    )
                )

        host_bridges = {
            bridge.get("name")
            for bridge in host.get("network", {}).get("bridges", []) or []
            if bridge.get("name")
        }
        for index, interface in enumerate(vm.get("network", {}).get("interfaces", []) or []):
            bridge_name = interface.get("bridge")
            if bridge_name and bridge_name not in host_bridges:
                errors.append(
                    ValidationError(
                        "missing_host_bridge",
                        f"inventory/vms/{vm_name}.yaml.network.interfaces[{index}].bridge",
                        f"VM {vm_name} uses bridge {bridge_name} not declared by Host {host_name}",
                    )
                )

    return errors
