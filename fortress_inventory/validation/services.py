from fortress_services.runtime_intent import analyze_service_runtime_intent

from .errors import ValidationError


BACKEND_RUNTIME_DIAGNOSTICS = {
    "service_backend_not_singular",
    "missing_service_backend_vm",
    "backend_port_collision",
}
PUBLISHED_PORT_RUNTIME_DIAGNOSTICS = {
    "published_port_collision",
    "invalid_ingress_published_port",
    "missing_ingress_published_port",
}
TELEMETRY_TARGET_RUNTIME_DIAGNOSTICS = {
    "missing_telemetry_target_published_port",
    "unreachable_telemetry_target_published_port",
}
SERVICE_OBSERVABILITY_VIEW_PROFILES = {"prometheus_generic"}


def validate_service_ingress_contract(model):
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


def validate_ingress_dns_targets(model):
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


def validate_service_backends(model):
    return _runtime_diagnostics_as_validation_errors(
        analyze_service_runtime_intent(model),
        BACKEND_RUNTIME_DIAGNOSTICS,
    )


def validate_quadlet_services(model):
    errors = []
    errors.extend(_validate_published_ports(model))
    errors.extend(_validate_service_telemetry_targets(model))
    errors.extend(validate_service_observability_view_requests(model))
    errors.extend(_validate_service_images(model))
    errors.extend(_validate_service_networks(model))
    errors.extend(_validate_container_dependencies(model))
    errors.extend(_validate_service_secrets(model))
    return errors


def validate_service_observability_view_requests(model):
    errors = []
    for service_name, service in model.services.items():
        instrumentation = service.get("instrumentation") or {}
        requests = instrumentation.get("observability_views") or []
        if len(requests) > 1:
            errors.append(
                ValidationError(
                    "multiple_service_observability_view_requests",
                    f"inventory/services/{service_name}.yaml.instrumentation.observability_views",
                    f"Service {service_name} requests more than one Service-level Observability View",
                )
            )
        telemetry_targets = instrumentation.get("telemetry_targets") or []
        for request_index, request in enumerate(requests):
            profile = request.get("profile") if isinstance(request, dict) else None
            path = f"inventory/services/{service_name}.yaml.instrumentation.observability_views[{request_index}].profile"
            if profile not in SERVICE_OBSERVABILITY_VIEW_PROFILES:
                errors.append(
                    ValidationError(
                        "unsupported_service_observability_view_profile",
                        path,
                        f"Service {service_name} requests unsupported Observability View Profile {profile}",
                    )
                )
                continue
            if profile == "prometheus_generic" and not any(
                target.get("type") == "prometheus_metrics"
                for target in telemetry_targets
                if isinstance(target, dict)
            ):
                errors.append(
                    ValidationError(
                        "incompatible_service_observability_view_profile",
                        path,
                        (
                            f"Service {service_name} requests prometheus_generic Observability View Profile "
                            "without a prometheus_metrics Telemetry Target"
                        ),
                    )
                )
    return errors


def validate_native_services(model):
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
    return _runtime_diagnostics_as_validation_errors(
        analyze_service_runtime_intent(model),
        PUBLISHED_PORT_RUNTIME_DIAGNOSTICS,
    )


def _validate_service_telemetry_targets(model):
    return _runtime_diagnostics_as_validation_errors(
        analyze_service_runtime_intent(model),
        TELEMETRY_TARGET_RUNTIME_DIAGNOSTICS,
    )


def _runtime_diagnostics_as_validation_errors(intent, codes):
    return [
        ValidationError(diagnostic.code, diagnostic.path, diagnostic.message)
        for diagnostic in intent.diagnostics
        if diagnostic.code in codes
    ]


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


def _validate_service_networks(model):
    errors = []
    network_backend_vms = {}
    aliases_by_network = {}
    for service_name, service in model.services.items():
        if service.get("deploy", {}).get("type") != "quadlet":
            continue
        group_name = service.get("service_group")
        network_name = service.get("service_network")
        backend = service.get("backend", {})
        backend_vm_name = backend.get("vm") if isinstance(backend, dict) else None
        if network_name:
            existing_vm = network_backend_vms.setdefault(network_name, backend_vm_name)
            if existing_vm != backend_vm_name:
                errors.append(
                    ValidationError(
                        "service_network_spans_backend_vms",
                        f"inventory/services/{service_name}.yaml.service_network",
                        f"Service Network {network_name} spans Backend VMs {existing_vm} and {backend_vm_name}",
                    )
                )
        if network_name:
            network_key = ("service_network", network_name)
            network_description = f"Service Network {network_name}"
        else:
            network_key = ("service", service_name)
            network_description = f"Service {service_name}"
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
                        f"in {network_description}",
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


def validate_service_hostnames(model):
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


def validate_service_share_backed_volumes(model):
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


def _service_volume_path(service_name, container_index, volume_index, field):
    return (
        f"inventory/services/{service_name}.yaml.deploy.containers"
        f"[{container_index}].volumes[{volume_index}].{field}"
    )
