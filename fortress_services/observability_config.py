from fortress_inventory.entity_graph import InventoryEntityGraph
from fortress_services.quadlet import ServiceDataFile


NODE_EXPORTER_PORT = 9100
PROMETHEUS_CONFIG_PATH = "/srv/services/observability/prometheus-config/prometheus.yml"
GENERATED_ENDPOINTS_PATH = "/srv/services/observability/generated-endpoints.yml"


def observability_service_data_files(model):
    graph = InventoryEntityGraph(model)
    telemetry_targets = graph.service_telemetry_target_facts()
    observability_service = model.services.get("observability") or {}
    owner = observability_service.get("service_data_owner") or {}
    http_probe_static_configs = [
        {
            "targets": [f"{target.scheme}://{target.vm_static_ipv4_address}:{target.published_port}{target.path}"],
            "labels": {
                "fortress_service": target.service_name,
                "fortress_telemetry_target": target.name,
            },
        }
        for target in telemetry_targets
        if target.target_type == "http_probe" and target.vm_static_ipv4_address
    ]
    prometheus_config = {
        "global": {"scrape_interval": "15s"},
        "scrape_configs": [
            {
                "job_name": "fortress-vm-node-exporter",
                "static_configs": [
                    {
                        "targets": [f"{vm.static_ipv4_address}:{NODE_EXPORTER_PORT}"],
                        "labels": {"fortress_vm": vm.vm_name},
                    }
                    for vm in graph.instrumented_vm_facts()
                    if vm.static_ipv4_address
                ],
            }
        ]
        + [
            {
                "job_name": f"fortress-service-{target.service_name}-{target.name}",
                "scheme": target.scheme,
                "metrics_path": target.path,
                "static_configs": [
                    {
                        "targets": [f"{target.vm_static_ipv4_address}:{target.published_port}"],
                        "labels": {
                            "fortress_service": target.service_name,
                            "fortress_telemetry_target": target.name,
                        },
                    }
                ],
            }
            for target in telemetry_targets
            if target.target_type == "prometheus_metrics" and target.vm_static_ipv4_address
        ]
        + (
            [
                {
                    "job_name": "fortress-service-http-probes",
                    "metrics_path": "/probe",
                    "params": {"module": ["http_2xx"]},
                    "static_configs": http_probe_static_configs,
                    "relabel_configs": [
                        {"source_labels": ["__address__"], "target_label": "__param_target"},
                        {"source_labels": ["__param_target"], "target_label": "instance"},
                        {"target_label": "__address__", "replacement": "blackbox:9115"},
                    ],
                }
            ]
            if http_probe_static_configs
            else []
        ),
    }
    observability_vm_name = (observability_service.get("backend") or {}).get("vm")
    observability_vm_address = graph.vm_static_ipv4_address(observability_vm_name)
    loki_port = _published_port_for_container(observability_service, "loki", 3100)
    return (
        ServiceDataFile(
            path=PROMETHEUS_CONFIG_PATH,
            content=_dump_yaml(prometheus_config),
            uid=owner.get("uid"),
            gid=owner.get("gid"),
            force=True,
        ),
        ServiceDataFile(
            path=GENERATED_ENDPOINTS_PATH,
            content=_dump_yaml(
                {
                    "loki": {
                        "host": observability_vm_address,
                        "port": loki_port,
                        "push_url": f"http://{observability_vm_address}:{loki_port}/loki/api/v1/push",
                    }
                }
            ),
            uid=owner.get("uid"),
            gid=owner.get("gid"),
            force=True,
        ),
    )


def _published_port_for_container(service, container_name, container_port):
    for container in service.get("deploy", {}).get("containers", []) or []:
        if container.get("name") != container_name:
            continue
        for published_port in container.get("published_ports", []) or []:
            if published_port.get("container") == container_port:
                return published_port.get("host", container_port)
    return container_port


def _dump_yaml(value, indent=0):
    lines = []
    _append_yaml(lines, value, indent)
    return "\n".join(lines) + "\n"


def _append_yaml(lines, value, indent):
    prefix = " " * indent
    if isinstance(value, dict):
        for key, item in value.items():
            if _is_scalar_list(item):
                lines.append(f"{prefix}{key}: [{', '.join(_yaml_scalar(entry) for entry in item)}]")
            elif isinstance(item, (dict, list)):
                lines.append(f"{prefix}{key}:")
                _append_yaml(lines, item, indent + 2)
            else:
                lines.append(f"{prefix}{key}: {_yaml_scalar(item)}")
        return
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                first_key, first_value = next(iter(item.items()))
                if _is_scalar_list(first_value):
                    lines.append(
                        f"{prefix}- {first_key}: [{', '.join(_yaml_scalar(entry) for entry in first_value)}]"
                    )
                elif isinstance(first_value, (dict, list)):
                    lines.append(f"{prefix}- {first_key}:")
                    _append_yaml(lines, first_value, indent + 2)
                else:
                    lines.append(f"{prefix}- {first_key}: {_yaml_scalar(first_value)}")
                for key, nested in list(item.items())[1:]:
                    if _is_scalar_list(nested):
                        lines.append(
                            f"{' ' * (indent + 2)}{key}: [{', '.join(_yaml_scalar(entry) for entry in nested)}]"
                        )
                    elif isinstance(nested, (dict, list)):
                        lines.append(f"{' ' * (indent + 2)}{key}:")
                        _append_yaml(lines, nested, indent + 4)
                    else:
                        lines.append(f"{' ' * (indent + 2)}{key}: {_yaml_scalar(nested)}")
            else:
                lines.append(f"{prefix}- {_yaml_scalar(item)}")
        return
    lines.append(f"{prefix}{_yaml_scalar(value)}")


def _yaml_scalar(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def _is_scalar_list(value):
    return isinstance(value, list) and all(not isinstance(item, (dict, list)) for item in value)
