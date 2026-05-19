"""Service Runtime Intent analysis for fortress-owned Service runtime meaning."""

from dataclasses import dataclass


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
class ServiceRuntimeIntent:
    backends: tuple[BackendRuntimeFact, ...]
    published_ports: tuple[PublishedPortRuntimeFact, ...]
    telemetry_targets: tuple[TelemetryTargetRuntimeFact, ...]
    diagnostics: tuple[RuntimeDiagnostic, ...]


def analyze_service_runtime_intent(model):
    backends = []
    published_ports = []
    telemetry_targets = []
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
            for container_index, container in enumerate(service.get("deploy", {}).get("containers", []) or []):
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

    return ServiceRuntimeIntent(
        backends=tuple(backends),
        published_ports=tuple(published_ports),
        telemetry_targets=tuple(telemetry_targets),
        diagnostics=tuple(diagnostics),
    )


def _published_port_protocols(protocol):
    if protocol == "tcp_udp":
        return ("tcp", "udp")
    return (protocol or "tcp",)


def _published_port_is_vm_reachable(published_port):
    return published_port.bind not in {"127.0.0.1", "localhost", "::1"}


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


def _default_telemetry_target_path(target_type):
    if target_type == "prometheus_metrics":
        return "/metrics"
    return "/"
