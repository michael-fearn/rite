"""Service Runtime Intent analysis for fortress-owned Service runtime meaning."""

import json
from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True)
class RuntimeDiagnostic:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class BackendRuntimeFact:
    service_name: str
    vm_name: str
    port: int


@dataclass(frozen=True)
class PublishedPortRuntimeFact:
    service_name: str
    vm_name: str
    container_name: str | None
    container_index: int
    port_index: int
    host_port: int
    container_port: int
    bind: str
    protocols: tuple[str, ...]
    ingress: bool


@dataclass(frozen=True)
class TelemetryTargetRuntimeFact:
    service_name: str
    vm_name: str
    name: str
    target_type: str
    published_port: int
    scheme: str
    path: str


@dataclass(frozen=True)
class ServiceSecretRuntimeFact:
    service_name: str
    container_name: str | None
    container_index: int
    secret_index: int
    secret_key: str
    podman_name: str
    env: str
    sops_extract: str
    env_value_mode: str


@dataclass(frozen=True)
class ServiceOwnedVolumeRuntimeFact:
    service_name: str
    vm_name: str
    container_name: str | None
    container_index: int
    volume_index: int
    service_path: str
    vm_path: str
    container_path: str | None
    access_mode: str
    uid: int | None = None
    gid: int | None = None


@dataclass(frozen=True)
class ServiceDataDirectoryRuntimeFact:
    service_name: str
    vm_name: str
    path: str
    uid: int | None = None
    gid: int | None = None


@dataclass(frozen=True)
class ShareBackedVolumeRuntimeFact:
    service_name: str
    vm_name: str
    container_name: str | None
    container_index: int
    volume_index: int
    mount_name: str
    dataset_name: str | None
    vm_mount_path: str | None
    resolved_source_path: str | None
    container_path: str | None
    access: str | None
    required_mount_unit: str | None


@dataclass(frozen=True)
class NativeEnvironmentSecretRuntimeFact:
    service_name: str
    secret_index: int
    secret_key: str
    env: str
    sops_extract: str


@dataclass(frozen=True)
class ServiceRuntimeIntent:
    backends: tuple[BackendRuntimeFact, ...]
    published_ports: tuple[PublishedPortRuntimeFact, ...]
    telemetry_targets: tuple[TelemetryTargetRuntimeFact, ...]
    service_secrets: tuple[ServiceSecretRuntimeFact, ...]
    service_owned_volumes: tuple[ServiceOwnedVolumeRuntimeFact, ...]
    service_data_directories: tuple[ServiceDataDirectoryRuntimeFact, ...]
    share_backed_volumes: tuple[ShareBackedVolumeRuntimeFact, ...]
    native_environment_secrets: tuple[NativeEnvironmentSecretRuntimeFact, ...]
    diagnostics: tuple[RuntimeDiagnostic, ...]


def service_runtime_intent_for_service(runtime_intent, service_name):
    return ServiceRuntimeIntent(
        backends=_facts_for_service(runtime_intent.backends, service_name),
        published_ports=_facts_for_service(runtime_intent.published_ports, service_name),
        telemetry_targets=_facts_for_service(runtime_intent.telemetry_targets, service_name),
        service_secrets=_facts_for_service(runtime_intent.service_secrets, service_name),
        service_owned_volumes=_facts_for_service(runtime_intent.service_owned_volumes, service_name),
        service_data_directories=_facts_for_service(runtime_intent.service_data_directories, service_name),
        share_backed_volumes=_facts_for_service(runtime_intent.share_backed_volumes, service_name),
        native_environment_secrets=_facts_for_service(runtime_intent.native_environment_secrets, service_name),
        diagnostics=tuple(
            diagnostic
            for diagnostic in runtime_intent.diagnostics
            if _diagnostic_for_service(diagnostic, service_name)
        ),
    )


def _facts_for_service(facts, service_name):
    return tuple(fact for fact in facts if fact.service_name == service_name)


def _diagnostic_for_service(diagnostic, service_name):
    return diagnostic.path.startswith(f"inventory/services/{service_name}.yaml")


def analyze_service_runtime_intent(model):
    backends = []
    published_ports = []
    telemetry_targets = []
    service_secrets = []
    service_owned_volumes = []
    service_data_directories = []
    seen_service_data_directories = set()
    share_backed_volumes = []
    native_environment_secrets = []
    diagnostics = []
    seen_backend_ports = {}
    seen_published_ports = {}
    for service_name, service in model.services.items():
        backend = service.get("backend", {})
        if not isinstance(backend, dict):
            diagnostics.append(
                RuntimeDiagnostic(
                    "service_backend_not_singular",
                    f"inventory/services/{service_name}.yaml.backend",
                    f"Service {service_name} must declare one singular Backend for issue 07",
                )
            )
            continue

        vm_name = backend.get("vm")
        port = backend.get("port")
        if vm_name and vm_name not in model.vms:
            diagnostics.append(
                RuntimeDiagnostic(
                    "missing_service_backend_vm",
                    f"inventory/services/{service_name}.yaml.backend.vm",
                    f"Service {service_name} references missing Backend VM {vm_name}",
                )
            )
        if vm_name and port:
            backends.append(BackendRuntimeFact(service_name, vm_name, port))
            key = (vm_name, port)
            if key in seen_backend_ports:
                other_service = seen_backend_ports[key]
                diagnostics.append(
                    RuntimeDiagnostic(
                        "backend_port_collision",
                        f"inventory/services/{service_name}.yaml.backend.port",
                        f"Services {other_service} and {service_name} both use Backend {vm_name}:{port}",
                    )
                )
            else:
                seen_backend_ports[key] = service_name

        service_published_ports = []
        ingress_backend_matches = []
        deploy_type = service.get("deploy", {}).get("type")
        if deploy_type == "quadlet":
            backend_vm = model.vms.get(vm_name) if vm_name else None
            mount_by_name = {
                mount.get("name"): mount
                for mount in (backend_vm or {}).get("mounts", []) or []
                if mount.get("name")
            }
            for container_index, container in enumerate(service.get("deploy", {}).get("containers", []) or []):
                owner = service.get("service_data_owner") or {}
                for volume_index, volume in enumerate(container.get("volumes", []) or []):
                    if volume.get("mount"):
                        mount_name = volume["mount"]
                        if _unsafe_share_backed_source(volume.get("source")):
                            diagnostics.append(
                                RuntimeDiagnostic(
                                    "unsafe_service_volume_source",
                                    _service_volume_path(service_name, container_index, volume_index, "source"),
                                    f"Service {service_name} Share-backed Volume source {volume.get('source')} "
                                    "must be / or a relative subpath without .. traversal",
                                )
                            )
                        mount = mount_by_name.get(mount_name)
                        if not mount:
                            diagnostics.append(
                                RuntimeDiagnostic(
                                    "missing_service_volume_mount",
                                    _service_volume_path(service_name, container_index, volume_index, "mount"),
                                    f"Service {service_name} Share-backed Volume references missing Mount Name "
                                    f"{mount_name} on Backend VM {vm_name}",
                                )
                            )
                            continue
                        if mount.get("access") == "read_only" and volume.get("access") == "read_write":
                            diagnostics.append(
                                RuntimeDiagnostic(
                                    "service_volume_widens_mount_access",
                                    _service_volume_path(service_name, container_index, volume_index, "access"),
                                    f"Service {service_name} Share-backed Volume cannot widen read-only "
                                    f"Mount {mount_name} to read_write",
                                )
                            )
                        share_backed_volumes.append(
                            ShareBackedVolumeRuntimeFact(
                                service_name=service_name,
                                vm_name=vm_name,
                                container_name=container.get("name"),
                                container_index=container_index,
                                volume_index=volume_index,
                                mount_name=mount_name,
                                dataset_name=mount.get("dataset"),
                                vm_mount_path=mount.get("mount_point"),
                                resolved_source_path=_share_backed_source_path(
                                    mount.get("mount_point"),
                                    volume.get("source"),
                                ),
                                container_path=volume.get("container"),
                                access=volume.get("access", mount.get("access")),
                                required_mount_unit=systemd_mount_unit_name(mount.get("mount_point")),
                            )
                        )
                        continue
                    if "service_path" not in volume:
                        continue
                    service_path = volume["service_path"]
                    vm_path = str(PurePosixPath("/srv/services") / service_name / service_path)
                    service_owned_volumes.append(
                        ServiceOwnedVolumeRuntimeFact(
                            service_name=service_name,
                            vm_name=vm_name,
                            container_name=container.get("name"),
                            container_index=container_index,
                            volume_index=volume_index,
                            service_path=service_path,
                            vm_path=vm_path,
                            container_path=volume.get("container"),
                            access_mode=_volume_access_mode(volume),
                            uid=owner.get("uid"),
                            gid=owner.get("gid"),
                        )
                    )
                    directory_key = (service_name, vm_path)
                    if directory_key not in seen_service_data_directories:
                        seen_service_data_directories.add(directory_key)
                        service_data_directories.append(
                            ServiceDataDirectoryRuntimeFact(
                                service_name=service_name,
                                vm_name=vm_name,
                                path=vm_path,
                                uid=owner.get("uid"),
                                gid=owner.get("gid"),
                            )
                        )
                for secret_index, secret in enumerate(container.get("secrets", []) or []):
                    diagnostics.extend(
                        _service_secret_diagnostics(service_name, container_index, secret_index, secret)
                    )
                    service_secrets.append(
                        service_secret_runtime_fact(service_name, container_index, container, secret_index, secret)
                    )
                for port_index, published_port in enumerate(container.get("published_ports", []) or []):
                    container_port = published_port.get("container")
                    host_port = published_port.get("host", container_port)
                    if not (vm_name and host_port and container_port):
                        continue
                    protocols = _published_port_protocols(published_port.get("protocol", "tcp"))
                    fact = PublishedPortRuntimeFact(
                        service_name=service_name,
                        vm_name=vm_name,
                        container_name=container.get("name"),
                        container_index=container_index,
                        port_index=port_index,
                        host_port=host_port,
                        container_port=container_port,
                        bind=published_port.get("bind", "127.0.0.1"),
                        protocols=protocols,
                        ingress=published_port.get("ingress") is True,
                    )
                    published_ports.append(fact)
                    service_published_ports.append(fact)
                    if fact.ingress and fact.host_port == port and "tcp" in fact.protocols:
                        ingress_backend_matches.append(fact)
                    for protocol in protocols:
                        key = (vm_name, host_port, protocol)
                        if key in seen_published_ports:
                            other_service = seen_published_ports[key].service_name
                            diagnostics.append(
                                RuntimeDiagnostic(
                                    "published_port_collision",
                                    _service_published_port_path(service_name, container_index, port_index, "host"),
                                    f"Services {other_service} and {service_name} both publish "
                                    f"{protocol.upper()} port {host_port} on Backend VM {vm_name}",
                                )
                            )
                        else:
                            seen_published_ports[key] = fact
        published_ports_by_host_port = {}
        for published_port in service_published_ports:
            published_ports_by_host_port.setdefault(published_port.host_port, []).append(published_port)
        for target_index, target in enumerate(
            service.get("instrumentation", {}).get("telemetry_targets", []) or []
        ):
            published_port = target.get("published_port")
            matching_published_ports = published_ports_by_host_port.get(published_port, [])
            if not matching_published_ports:
                diagnostics.append(
                    RuntimeDiagnostic(
                        "missing_telemetry_target_published_port",
                        _service_telemetry_target_path(service_name, target_index, "published_port"),
                        f"Service {service_name} Telemetry Target {target.get('name', target_index)} "
                        f"references undeclared Published Port {published_port}",
                    )
                )
                continue
            reachable_published_ports = [
                candidate
                for candidate in matching_published_ports
                if "tcp" in candidate.protocols and _published_port_is_vm_reachable(candidate)
            ]
            if not reachable_published_ports:
                diagnostics.append(
                    RuntimeDiagnostic(
                        "unreachable_telemetry_target_published_port",
                        _service_telemetry_target_path(service_name, target_index, "published_port"),
                        f"Service {service_name} Telemetry Target {target.get('name', target_index)} "
                        f"references Published Port {published_port}, but it is not VM-reachable",
                    )
                )
                continue
            telemetry_targets.append(
                TelemetryTargetRuntimeFact(
                    service_name=service_name,
                    vm_name=vm_name,
                    name=target.get("name"),
                    target_type=target.get("type"),
                    published_port=published_port,
                    scheme=target.get("scheme", "http"),
                    path=target.get("path", _default_telemetry_target_path(target.get("type"))),
                )
            )
        if deploy_type == "quadlet" and service.get("ingress", {}).get("enabled") and port:
            if len(ingress_backend_matches) != 1:
                diagnostics.append(
                    RuntimeDiagnostic(
                        "invalid_ingress_published_port",
                        f"inventory/services/{service_name}.yaml.backend.port",
                        f"Service {service_name} enables Ingress but must have exactly one TCP-capable "
                        f"Published Port marked for Ingress on Backend port {port}",
                    )
                )
            if not ingress_backend_matches:
                diagnostics.append(
                    RuntimeDiagnostic(
                        "missing_ingress_published_port",
                        f"inventory/services/{service_name}.yaml.backend.port",
                        f"Service {service_name} enables Ingress but no Published Port explicitly marks "
                        f"Backend port {port} with ingress: true",
                    )
                )
        if deploy_type == "native":
            for secret_index, secret in enumerate(service.get("deploy", {}).get("environment_secrets", []) or []):
                secret_ref = secret.get("secret")
                if secret_ref and not secret_ref.startswith("secrets."):
                    diagnostics.append(
                        RuntimeDiagnostic(
                            "native_environment_secret_reference_not_sibling_sops_secret",
                            _native_environment_secret_path(service_name, secret_index, "secret"),
                            (
                                f"Service {service_name} Native Service Environment Secret references "
                                "must use secrets.<name>"
                            ),
                        )
                    )
                    continue
                if not secret_ref:
                    continue
                secret_key = _service_secret_key(secret)
                native_environment_secrets.append(
                    NativeEnvironmentSecretRuntimeFact(
                        service_name=service_name,
                        secret_index=secret_index,
                        secret_key=secret_key,
                        env=secret.get("env"),
                        sops_extract=_sops_extract_path("secrets", secret_key, "value"),
                    )
                )

    return ServiceRuntimeIntent(
        backends=tuple(backends),
        published_ports=tuple(published_ports),
        telemetry_targets=tuple(telemetry_targets),
        service_secrets=tuple(service_secrets),
        service_owned_volumes=tuple(service_owned_volumes),
        service_data_directories=tuple(service_data_directories),
        share_backed_volumes=tuple(share_backed_volumes),
        native_environment_secrets=tuple(native_environment_secrets),
        diagnostics=tuple(diagnostics),
    )


def _published_port_protocols(protocol):
    if protocol == "tcp_udp":
        return ("tcp", "udp")
    return (protocol or "tcp",)


def _published_port_is_vm_reachable(published_port):
    return published_port.bind not in {"127.0.0.1", "localhost", "::1"}


def _volume_access_mode(volume):
    return "ro" if volume.get("access") == "read_only" else "rw"


def _share_backed_source_path(mount_point, source):
    if not mount_point or source in (None, "/"):
        return mount_point
    return str(PurePosixPath(mount_point) / source)


def _unsafe_share_backed_source(source):
    if source == "/":
        return False
    if not source or str(source).startswith("/"):
        return True
    return ".." in str(source).split("/")


def systemd_mount_unit_name(mount_point):
    normalized = "/".join(part for part in str(mount_point).split("/") if part)
    if not normalized:
        return "-.mount"

    escaped = []
    at_start = True
    for char in normalized:
        if char == "/":
            escaped.append("-")
            at_start = True
            continue
        escaped.append(_escape_systemd_path_char(char, at_start))
        at_start = False
    return f"{''.join(escaped)}.mount"


def _escape_systemd_path_char(char, at_start):
    allowed = char.isalnum() or char in ":_."
    if allowed and not (at_start and char == "."):
        return char
    return "".join(f"\\x{byte:02x}" for byte in char.encode())


def _service_published_port_path(service_name, container_index, port_index, field):
    return (
        f"inventory/services/{service_name}.yaml.deploy.containers"
        f"[{container_index}].published_ports[{port_index}].{field}"
    )


def _service_telemetry_target_path(service_name, target_index, field):
    return (
        f"inventory/services/{service_name}.yaml.instrumentation."
        f"telemetry_targets[{target_index}].{field}"
    )


def _service_volume_path(service_name, container_index, volume_index, field):
    return (
        f"inventory/services/{service_name}.yaml.deploy.containers"
        f"[{container_index}].volumes[{volume_index}].{field}"
    )


def _default_telemetry_target_path(target_type):
    if target_type == "prometheus_metrics":
        return "/metrics"
    return "/"


def _service_secret_key(secret):
    reference = secret["secret"]
    if not reference.startswith("secrets."):
        return reference
    return reference.split(".", 1)[1]


def service_secret_runtime_fact(service_name, container_index, container, secret_index, secret):
    secret_key = _service_secret_key(secret)
    return ServiceSecretRuntimeFact(
        service_name=service_name,
        container_name=container.get("name"),
        container_index=container_index,
        secret_index=secret_index,
        secret_key=secret_key,
        podman_name=f"fortress_{service_name}_{secret_key}",
        env=secret.get("env"),
        sops_extract=_sops_extract_path("secrets", secret_key, "value"),
        env_value_mode=secret.get("env_value", "file_path"),
    )


def service_secret_runtime_facts_for_service(service):
    service_name = service["name"]
    facts = []
    for container_index, container in enumerate(service.get("deploy", {}).get("containers", []) or []):
        for secret_index, secret in enumerate(container.get("secrets", []) or []):
            facts.append(service_secret_runtime_fact(service_name, container_index, container, secret_index, secret))
    return tuple(facts)


def _service_secret_diagnostics(service_name, container_index, secret_index, secret):
    diagnostics = []
    if secret.get("secret") and not secret["secret"].startswith("secrets."):
        diagnostics.append(
            RuntimeDiagnostic(
                "service_secret_reference_not_sibling_sops_secret",
                _service_secret_path(service_name, container_index, secret_index, "secret"),
                f"Service {service_name} Service Secret references must use secrets.<name>",
            )
        )
    env_value_mode = secret.get("env_value", "file_path")
    if secret.get("env") and env_value_mode == "file_path" and not secret["env"].endswith("_FILE"):
        diagnostics.append(
            RuntimeDiagnostic(
                "service_secret_env_not_file",
                _service_secret_path(service_name, container_index, secret_index, "env"),
                f"Service {service_name} Service Secret env {secret['env']} must end in _FILE",
            )
        )
    return diagnostics


def _service_secret_path(service_name, container_index, secret_index, field):
    return (
        f"inventory/services/{service_name}.yaml.deploy.containers"
        f"[{container_index}].secrets[{secret_index}].{field}"
    )


def _native_environment_secret_path(service_name, secret_index, field):
    return (
        f"inventory/services/{service_name}.yaml.deploy."
        f"environment_secrets[{secret_index}].{field}"
    )


def _sops_extract_path(*segments):
    return "".join(f"[{json.dumps(segment)}]" for segment in segments)
