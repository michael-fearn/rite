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
    errors.extend(_validate_service_ingress_contract(model))
    errors.extend(_validate_ingress_dns_targets(model))
    errors.extend(_validate_service_hostnames(model))
    errors.extend(_validate_host_ingress_routes(model))
    errors.extend(_validate_quadlet_services(model))
    errors.extend(_validate_native_services(model))
    errors.extend(_validate_service_share_backed_volumes(model))
    errors.extend(_validate_vm_inventory_policy(model))
    errors.extend(_validate_vm_refs(model))
    errors.extend(_validate_dataset_names(model))
    errors.extend(_validate_dataset_nas_refs(model))
    errors.extend(_validate_dataset_lifecycle_policy(model, allow_ephemeral_datasets=allow_ephemeral_datasets))
    errors.extend(_validate_vm_mounts(model))
    errors.extend(_validate_vm_host_resources(model))
    return errors


def _validate_service_ingress_contract(model):
    errors = []
    for service_name, service in model.services.items():
        ingress = service.get("ingress")
        if isinstance(ingress, dict) and "enabled" not in ingress:
            errors.append(
                ValidationError(
                    "missing_service_ingress_enabled",
                    f"inventory/services/{service_name}.yaml.ingress.enabled",
                    f"Service {service_name} declares Ingress but does not declare ingress.enabled",
                )
            )
        if service.get("hostname") and not service.get("ingress", {}).get("enabled"):
            errors.append(
                ValidationError(
                    "service_hostname_without_ingress",
                    f"inventory/services/{service_name}.yaml.hostname",
                    f"Service {service_name} declares a hostname but does not enable Ingress",
                )
            )
    return errors


def _validate_ingress_dns_targets(model):
    errors = []
    for service_name, service in model.services.items():
        dns = service.get("dns") or {}
        if not dns.get("ingress_records", {}).get("enabled"):
            continue
        provider = dns.get("provider")
        if not provider:
            errors.append(
                ValidationError(
                    "missing_ingress_dns_target_provider",
                    f"inventory/services/{service_name}.yaml.dns.provider",
                    f"Service {service_name} enables Ingress DNS Records but does not declare dns.provider",
                )
            )
            continue
        if provider != "pihole":
            errors.append(
                ValidationError(
                    "unsupported_ingress_dns_target_provider",
                    f"inventory/services/{service_name}.yaml.dns.provider",
                    f"Service {service_name} declares unsupported Ingress DNS Target provider {provider}",
                )
            )
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
        if not isinstance(backend, dict):
            errors.append(
                ValidationError(
                    "service_backend_not_singular",
                    f"inventory/services/{service_name}.yaml.backend",
                    f"Service {service_name} must declare one singular Backend for issue 07",
                )
            )
            continue
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


def _validate_quadlet_services(model):
    errors = []
    errors.extend(_validate_published_ports(model))
    errors.extend(_validate_service_images(model))
    errors.extend(_validate_service_groups(model))
    errors.extend(_validate_container_dependencies(model))
    errors.extend(_validate_service_secrets(model))
    return errors


def _validate_native_services(model):
    errors = []
    apt_repos = model.globals.get("apt_repos") or {}
    for service_name, service in model.services.items():
        deploy = service.get("deploy", {})
        if deploy.get("type") != "native":
            continue
        apt_repo = deploy.get("apt_repo")
        if apt_repo and apt_repo not in apt_repos:
            errors.append(
                ValidationError(
                    "missing_native_service_apt_repo",
                    f"inventory/services/{service_name}.yaml.deploy.apt_repo",
                    f"Service {service_name} references missing apt repository {apt_repo}",
                )
            )
        for secret_index, secret in enumerate(deploy.get("environment_secrets", []) or []):
            secret_ref = secret.get("secret")
            if secret_ref and not secret_ref.startswith("secrets."):
                errors.append(
                    ValidationError(
                        "native_environment_secret_reference_not_sibling_sops_secret",
                        (
                            f"inventory/services/{service_name}.yaml.deploy."
                            f"environment_secrets[{secret_index}].secret"
                        ),
                        f"Service {service_name} Native Service Environment Secret references must use secrets.<name>",
                    )
                )
    return errors


def _validate_published_ports(model):
    errors = []
    seen = {}
    for service_name, service in model.services.items():
        if service.get("deploy", {}).get("type") != "quadlet":
            continue
        backend = service.get("backend", {})
        if not isinstance(backend, dict):
            continue
        backend_vm_name = backend.get("vm")
        backend_port = backend.get("port")
        ingress_backend_matches = []
        for container_index, container, port_index, published_port in _service_published_ports(service):
            host_port = published_port.get("host", published_port.get("container"))
            protocol = published_port.get("protocol", "tcp")
            if (
                published_port.get("ingress") is True
                and host_port == backend_port
                and "tcp" in _published_port_protocols(protocol)
            ):
                ingress_backend_matches.append((container_index, port_index))
            if backend_vm_name and host_port:
                for protocol_part in _published_port_protocols(protocol):
                    key = (backend_vm_name, host_port, protocol_part)
                    if key in seen:
                        other_service, other_container_index, other_port_index = seen[key]
                        errors.append(
                            ValidationError(
                                "published_port_collision",
                                _service_published_port_path(service_name, container_index, port_index, "host"),
                                f"Services {other_service} and {service_name} both publish "
                                f"{protocol_part.upper()} port {host_port} on Backend VM {backend_vm_name}",
                            )
                        )
                    else:
                        seen[key] = (service_name, container_index, port_index)
        if service.get("ingress", {}).get("enabled") and backend_port:
            if len(ingress_backend_matches) != 1:
                errors.append(
                    ValidationError(
                        "invalid_ingress_published_port",
                        f"inventory/services/{service_name}.yaml.backend.port",
                        f"Service {service_name} enables Ingress but must have exactly one TCP-capable "
                        f"Published Port marked for Ingress on Backend port {backend_port}",
                    )
                )
            if not ingress_backend_matches:
                errors.append(
                    ValidationError(
                        "missing_ingress_published_port",
                        f"inventory/services/{service_name}.yaml.backend.port",
                        f"Service {service_name} enables Ingress but no Published Port explicitly marks "
                        f"Backend port {backend_port} with ingress: true",
                    )
                )
    return errors


def _published_port_protocols(protocol):
    if protocol == "tcp_udp":
        return ("tcp", "udp")
    return (protocol or "tcp",)


def _validate_service_images(model):
    errors = []
    for service_name, service in model.services.items():
        if service.get("deploy", {}).get("type") != "quadlet":
            continue
        for container_index, container in enumerate(service.get("deploy", {}).get("containers", []) or []):
            image = container.get("image")
            if image and not _image_is_pinned(image):
                errors.append(
                    ValidationError(
                        "unpinned_service_image",
                        f"inventory/services/{service_name}.yaml.deploy.containers[{container_index}].image",
                        f"Service {service_name} container {container.get('name', container_index)} "
                        f"uses unpinned image {image}",
                    )
                )
    return errors


def _image_is_pinned(image):
    if "@sha256:" in image:
        return True
    remainder = image.rsplit("/", 1)[-1]
    if ":" not in remainder:
        return False
    return not remainder.endswith(":latest")


def _validate_service_groups(model):
    errors = []
    group_backend_vms = {}
    aliases_by_network = {}
    for service_name, service in model.services.items():
        if service.get("deploy", {}).get("type") != "quadlet":
            continue
        group_name = service.get("service_group")
        backend = service.get("backend", {})
        backend_vm_name = backend.get("vm") if isinstance(backend, dict) else None
        if group_name:
            existing_vm = group_backend_vms.setdefault(group_name, backend_vm_name)
            if existing_vm != backend_vm_name:
                errors.append(
                    ValidationError(
                        "service_group_spans_backend_vms",
                        f"inventory/services/{service_name}.yaml.service_group",
                        f"Service Group {group_name} spans Backend VMs {existing_vm} and {backend_vm_name}",
                    )
                )
            network_key = ("service_group", group_name)
        else:
            network_key = ("service", service_name)
        aliases = aliases_by_network.setdefault(network_key, {})
        for container_index, container in enumerate(service.get("deploy", {}).get("containers", []) or []):
            alias = container.get("name")
            if not alias:
                continue
            if alias in aliases:
                other_service = aliases[alias]
                errors.append(
                    ValidationError(
                        "container_alias_collision",
                        f"inventory/services/{service_name}.yaml.deploy.containers[{container_index}].name",
                        f"Services {other_service} and {service_name} both declare Container Alias {alias} "
                        f"in the same network namespace",
                    )
                )
            else:
                aliases[alias] = service_name
    return errors


def _validate_container_dependencies(model):
    errors = []
    for service_name, service in model.services.items():
        if service.get("deploy", {}).get("type") != "quadlet":
            continue
        containers = service.get("deploy", {}).get("containers", []) or []
        container_names = {container.get("name") for container in containers if container.get("name")}
        graph = {}
        for container_index, container in enumerate(containers):
            container_name = container.get("name")
            graph[container_name] = list(container.get("depends_on", []) or [])
            for dependency in graph[container_name]:
                if dependency not in container_names:
                    errors.append(
                        ValidationError(
                            "missing_container_dependency",
                            f"inventory/services/{service_name}.yaml.deploy.containers[{container_index}].depends_on",
                            f"Service {service_name} container {container_name} depends on missing "
                            f"same-Service container {dependency}",
                        )
                    )
        if _has_dependency_cycle(graph):
            errors.append(
                ValidationError(
                    "container_dependency_cycle",
                    f"inventory/services/{service_name}.yaml.deploy.containers",
                    f"Service {service_name} has a Container Dependency cycle",
                )
            )
    return errors


def _has_dependency_cycle(graph):
    visiting = set()
    visited = set()

    def visit(container_name):
        if container_name in visiting:
            return True
        if container_name in visited:
            return False
        visiting.add(container_name)
        for dependency in graph.get(container_name, []):
            if dependency in graph and visit(dependency):
                return True
        visiting.remove(container_name)
        visited.add(container_name)
        return False

    return any(visit(container_name) for container_name in graph)


def _validate_service_secrets(model):
    errors = []
    for service_name, service in model.services.items():
        if service.get("deploy", {}).get("type") != "quadlet":
            continue
        for container_index, container in enumerate(service.get("deploy", {}).get("containers", []) or []):
            env_names = set((container.get("env") or {}).keys())
            secret_env_names = set()
            for secret_index, secret in enumerate(container.get("secrets", []) or []):
                secret_ref = secret.get("secret")
                secret_env = secret.get("env")
                if secret_ref and not secret_ref.startswith("secrets."):
                    errors.append(
                        ValidationError(
                            "service_secret_reference_not_sibling_sops_secret",
                            _service_secret_path(service_name, container_index, secret_index, "secret"),
                            f"Service {service_name} Service Secret references must use secrets.<name>",
                        )
                    )
                if secret_env and not secret_env.endswith("_FILE"):
                    errors.append(
                        ValidationError(
                            "service_secret_env_not_file",
                            _service_secret_path(service_name, container_index, secret_index, "env"),
                            f"Service {service_name} Service Secret env {secret_env} must end in _FILE",
                        )
                    )
                if secret_env in secret_env_names:
                    errors.append(
                        ValidationError(
                            "service_env_conflict",
                            _service_secret_path(service_name, container_index, secret_index, "env"),
                            f"Service {service_name} container {container.get('name', container_index)} "
                            f"declares duplicate generated environment variable {secret_env}",
                        )
                    )
                secret_env_names.add(secret_env)

            conflict = sorted(env_names & secret_env_names)
            if conflict:
                errors.append(
                    ValidationError(
                        "service_env_conflict",
                        f"inventory/services/{service_name}.yaml.deploy.containers[{container_index}].env",
                        f"Service {service_name} container {container.get('name', container_index)} "
                        f"declares environment variable {conflict[0]} both as env and as a Service Secret",
                    )
                )

            fragment_env_names = _quadlet_fragment_environment_names(model, service_name, container)
            conflict = sorted((env_names | secret_env_names) & fragment_env_names)
            if conflict:
                errors.append(
                    ValidationError(
                        "service_env_conflict",
                        f"inventory/services/{service_name}.quadlet.d/{container.get('name')}.container",
                        f"Service {service_name} Quadlet Fragment cannot override environment variable "
                        f"{conflict[0]} owned by Service yaml",
                    )
                )
    return errors


def _quadlet_fragment_environment_names(model, service_name, container):
    root = getattr(model, "root", None)
    if root is None:
        return set()
    fragment_path = (
        root
        / "inventory"
        / "services"
        / f"{service_name}.quadlet.d"
        / f"{container.get('name')}.container"
    )
    if not fragment_path.is_file():
        return set()
    names = set()
    section = None
    for raw_line in fragment_path.read_text().splitlines():
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if section != "Container" or not line.startswith("Environment="):
            continue
        assignment = line.split("=", 1)[1]
        if "=" in assignment:
            names.add(assignment.split("=", 1)[0])
    return names


def _service_secret_path(service_name, container_index, secret_index, field):
    return (
        f"inventory/services/{service_name}.yaml.deploy.containers"
        f"[{container_index}].secrets[{secret_index}].{field}"
    )


def _validate_service_hostnames(model):
    errors = []
    seen = {}
    domain = model.globals.get("domain")
    for service_name, service in model.services.items():
        if service.get("ingress", {}).get("enabled") and not service.get("hostname"):
            errors.append(
                ValidationError(
                    "missing_ingress_hostname",
                    f"inventory/services/{service_name}.yaml.hostname",
                    f"Service {service_name} enables Ingress but does not declare a hostname",
                )
            )
            continue
        if not service.get("ingress", {}).get("enabled"):
            continue
        hostname = service.get("hostname")
        if service.get("ingress", {}).get("exposure") == "lan_only" and domain and not _hostname_is_under_domain(hostname, domain):
            errors.append(
                ValidationError(
                    "service_ingress_hostname_not_fleet_fqdn",
                    f"inventory/services/{service_name}.yaml.hostname",
                    f"LAN-only Service Ingress hostname {hostname} must be an explicit FQDN under {domain}",
                )
            )
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


def _hostname_is_under_domain(hostname, domain):
    if not isinstance(hostname, str) or not hostname.endswith(f".{domain}"):
        return False
    labels = hostname.split(".")
    return all(labels) and len(labels) > len(domain.split("."))


def _validate_host_ingress_routes(model):
    errors = []
    domain = model.globals.get("domain")
    trusted_source_ranges = (model.globals.get("ingress") or {}).get("trusted_source_ranges") or []
    seen_hostnames = {
        service.get("hostname"): f"Service {service_name}"
        for service_name, service in model.services.items()
        if service.get("ingress", {}).get("enabled") and service.get("hostname")
    }
    for host_name, host in model.hosts.items():
        route = host.get("ingress", {}).get("proxmox_web_ui", {})
        if not route.get("enabled"):
            continue
        hostname = route.get("hostname")
        if not host.get("network", {}).get("management_address"):
            errors.append(
                ValidationError(
                    "missing_host_ingress_management_address",
                    f"inventory/hosts/{host_name}.yaml.network.management_address",
                    f"Host Ingress Route for {host_name} must target the Host management address",
                )
            )
        if hostname in seen_hostnames:
            errors.append(
                ValidationError(
                    "duplicate_ingress_hostname",
                    f"inventory/hosts/{host_name}.yaml.ingress.proxmox_web_ui.hostname",
                    f"{seen_hostnames[hostname]} and Host Ingress Route {host_name} both publish hostname {hostname}",
                )
            )
        elif hostname:
            seen_hostnames[hostname] = f"Host Ingress Route {host_name}"
        expected_hostname = f"{host_name}.{domain}" if domain else None
        if hostname and expected_hostname and hostname != expected_hostname:
            errors.append(
                ValidationError(
                    "host_ingress_hostname_mismatch",
                    f"inventory/hosts/{host_name}.yaml.ingress.proxmox_web_ui.hostname",
                    f"Host Ingress Route for {host_name} must use hostname {expected_hostname}",
                )
            )
        if not trusted_source_ranges:
            errors.append(
                ValidationError(
                    "missing_host_ingress_trusted_source_ranges",
                    "inventory/group_vars/all.yaml.ingress.trusted_source_ranges",
                    f"Host Ingress Route for {host_name} is Trusted-only but no Trusted source ranges are declared",
                )
            )
    return errors


def _validate_service_share_backed_volumes(model):
    errors = []
    for service_name, service in model.services.items():
        backend = service.get("backend", {})
        if not isinstance(backend, dict):
            continue
        backend_vm_name = backend.get("vm")
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


def _service_published_ports(service):
    containers = service.get("deploy", {}).get("containers", []) or []
    for container_index, container in enumerate(containers):
        for port_index, published_port in enumerate(container.get("published_ports", []) or []):
            yield container_index, container, port_index, published_port


def _service_volume_path(service_name, container_index, volume_index, field):
    return (
        f"inventory/services/{service_name}.yaml.deploy.containers"
        f"[{container_index}].volumes[{volume_index}].{field}"
    )


def _service_published_port_path(service_name, container_index, port_index, field):
    return (
        f"inventory/services/{service_name}.yaml.deploy.containers"
        f"[{container_index}].published_ports[{port_index}].{field}"
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
    acceptance_dataset_names = {
        policy.get("dataset")
        for policy in model.acceptance_policies.values()
        if policy.get("dataset")
    }
    for dataset_file, dataset in model.datasets.items():
        if dataset.get("lifecycle") == "ephemeral" and dataset.get("name") not in acceptance_dataset_names:
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
