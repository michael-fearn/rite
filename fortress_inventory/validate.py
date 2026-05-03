from dataclasses import dataclass

from .model import load_inventory_tree


@dataclass(frozen=True)
class ValidationError:
    code: str
    path: str
    message: str


def validate_inventory_tree(root):
    return validate_inventory_model(load_inventory_tree(root))


def validate_inventory_model(model):
    errors = []
    errors.extend(_validate_service_backends(model))
    errors.extend(_validate_service_hostnames(model))
    errors.extend(_validate_vm_refs(model))
    errors.extend(_validate_nfs_exports(model))
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


def _validate_nfs_exports(model):
    errors = []
    exports = set(model.globals.get("nas", {}).get("exports", {}).keys())
    for vm_name, vm in model.vms.items():
        for index, mount in enumerate(vm.get("nfs_mounts", []) or []):
            export_name = mount.get("export")
            if export_name and export_name not in exports:
                errors.append(
                    ValidationError(
                        "missing_nfs_export",
                        f"inventory/vms/{vm_name}.yaml.nfs_mounts[{index}].export",
                        f"VM {vm_name} mounts missing Export {export_name}",
                    )
                )
    return errors
