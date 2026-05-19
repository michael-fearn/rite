import json
import os

from fortress_inventory.entity_graph import InventoryEntityGraph
from fortress_services.quadlet import ServiceDataFile


NODE_EXPORTER_PORT = 9100
PROMETHEUS_CONFIG_PATH = "/srv/services/observability/prometheus-config/prometheus.yml"
GENERATED_ENDPOINTS_PATH = "/srv/services/observability/generated-endpoints.yml"
GRAFANA_DASHBOARD_PROVIDER_PATH = (
    "/srv/services/observability/grafana-provisioning/dashboards/fortress-generated.yml"
)
GRAFANA_GENERATED_DASHBOARD_DIR = "/srv/services/observability/grafana-dashboards/generated"
GRAFANA_CONTAINER_GENERATED_DASHBOARD_DIR = "/var/lib/grafana/dashboards/fortress-generated"
GRAFANA_GENERATED_FOLDER_TITLE = "Rite Generated Observability"
GRAFANA_GENERATED_FOLDER_UID = "fortress-generated-observability"


def observability_service_data_files(model):
    graph = InventoryEntityGraph(model)
    excluded_vm_names = _excluded_vm_names()
    telemetry_targets = [
        target
        for target in graph.service_telemetry_target_facts()
        if target.vm_name not in excluded_vm_names
    ]
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
                    if vm.vm_name not in excluded_vm_names and vm.static_ipv4_address
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
    grafana_provider = {
        "apiVersion": 1,
        "providers": [
            {
                "name": "fortress-generated-observability-views",
                "orgId": 1,
                "folder": GRAFANA_GENERATED_FOLDER_TITLE,
                "folderUid": GRAFANA_GENERATED_FOLDER_UID,
                "type": "file",
                "disableDeletion": False,
                "editable": False,
                "allowUiUpdates": False,
                "options": {"path": GRAFANA_CONTAINER_GENERATED_DASHBOARD_DIR},
            }
        ],
    }
    grafana_dashboard_files = tuple(
        ServiceDataFile(
            path=f"{GRAFANA_GENERATED_DASHBOARD_DIR}/{_grafana_dashboard_filename(intent)}",
            content=_grafana_dashboard_json(intent, telemetry_targets),
            uid=owner.get("uid"),
            gid=owner.get("gid"),
            force=True,
        )
        for intent in graph.observability_view_intents(excluded_vm_names=excluded_vm_names)
    )
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
        ServiceDataFile(
            path=GRAFANA_DASHBOARD_PROVIDER_PATH,
            content=_dump_yaml(grafana_provider),
            uid=owner.get("uid"),
            gid=owner.get("gid"),
            force=True,
        ),
    ) + grafana_dashboard_files


def _published_port_for_container(service, container_name, container_port):
    for container in service.get("deploy", {}).get("containers", []) or []:
        if container.get("name") != container_name:
            continue
        for published_port in container.get("published_ports", []) or []:
            if published_port.get("container") == container_port:
                return published_port.get("host", container_port)
    return container_port


def _excluded_vm_names():
    return {
        vm_name.strip()
        for vm_name in os.environ.get("FORTRESS_OBSERVABILITY_EXCLUDED_VMS", "").split(",")
        if vm_name.strip()
    }


def _grafana_dashboard_filename(intent):
    return f"{intent.view_id.replace(':', '-')}.json"


def _grafana_dashboard_json(intent, telemetry_targets):
    if intent.entity_kind == "vm" and intent.view_kind == "vm_baseline":
        return _grafana_vm_baseline_dashboard(intent)
    if (
        intent.entity_kind == "service"
        and intent.view_kind == "service_profile"
        and intent.profile == "prometheus_generic"
    ):
        return _grafana_prometheus_generic_service_dashboard(intent, telemetry_targets)
    return _grafana_dashboard_stub(intent)


def _grafana_dashboard_stub(intent):
    return (
        json.dumps(
            {
                "uid": _grafana_dashboard_uid(intent),
                "title": _grafana_dashboard_title(intent),
                "schemaVersion": 39,
                "version": 1,
                "refresh": "30s",
                "panels": [],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _grafana_vm_baseline_dashboard(intent):
    vm_name = intent.entity_name
    return (
        json.dumps(
            {
                "uid": _grafana_dashboard_uid(intent),
                "title": _grafana_dashboard_title(intent),
                "schemaVersion": 39,
                "version": 1,
                "refresh": "30s",
                "templating": {
                    "list": [
                        _grafana_datasource_variable("DS_PROMETHEUS", "prometheus"),
                        _grafana_datasource_variable("DS_LOKI", "loki"),
                    ]
                },
                "panels": [
                    _timeseries_panel(
                        panel_id=1,
                        title="CPU",
                        datasource_type="prometheus",
                        datasource_uid="${DS_PROMETHEUS}",
                        expr=(
                            '100 - (avg by (fortress_vm) '
                            f'(rate(node_cpu_seconds_total{{fortress_vm="{vm_name}", mode="idle"}}[5m])) * 100)'
                        ),
                    ),
                    _timeseries_panel(
                        panel_id=2,
                        title="Memory",
                        datasource_type="prometheus",
                        datasource_uid="${DS_PROMETHEUS}",
                        expr=(
                            f'100 * (1 - (node_memory_MemAvailable_bytes{{fortress_vm="{vm_name}"}} '
                            f'/ node_memory_MemTotal_bytes{{fortress_vm="{vm_name}"}}))'
                        ),
                    ),
                    _logs_panel(
                        panel_id=3,
                        title="System Logs",
                        datasource_uid="${DS_LOKI}",
                        expr=f'{{fortress_vm="{vm_name}"}}',
                    ),
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _grafana_prometheus_generic_service_dashboard(intent, telemetry_targets):
    service_name = intent.entity_name
    target_names = tuple(
        target.name
        for target in telemetry_targets
        if target.service_name == service_name and target.target_type == "prometheus_metrics"
    )
    target_selector = "|".join(
        _prometheus_regex_escape(target_name) for target_name in target_names
    )
    label_selector = (
        f'fortress_service="{service_name}", '
        f'fortress_telemetry_target=~"{target_selector}"'
    )
    return (
        json.dumps(
            {
                "uid": _grafana_dashboard_uid(intent),
                "title": _grafana_dashboard_title(intent),
                "schemaVersion": 39,
                "version": 1,
                "refresh": "30s",
                "templating": {
                    "list": [_grafana_datasource_variable("DS_PROMETHEUS", "prometheus")]
                },
                "panels": [
                    _timeseries_panel(
                        panel_id=1,
                        title="Service Request Rate",
                        datasource_type="prometheus",
                        datasource_uid="${DS_PROMETHEUS}",
                        expr=(
                            "sum by (fortress_telemetry_target) "
                            f"(rate(http_requests_total{{{label_selector}}}[5m]))"
                        ),
                    ),
                    _timeseries_panel(
                        panel_id=2,
                        title="Service Error Rate",
                        datasource_type="prometheus",
                        datasource_uid="${DS_PROMETHEUS}",
                        expr=(
                            "sum by (fortress_telemetry_target) "
                            f'(rate(http_requests_total{{{label_selector}, status=~"5.."}}[5m]))'
                        ),
                    ),
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _grafana_datasource_variable(name, datasource_type):
    return {
        "name": name,
        "type": "datasource",
        "query": datasource_type,
        "current": {},
        "hide": 0,
        "label": datasource_type.title(),
    }


def _timeseries_panel(panel_id, title, datasource_type, datasource_uid, expr):
    return {
        "id": panel_id,
        "title": title,
        "type": "timeseries",
        "datasource": {"type": datasource_type, "uid": datasource_uid},
        "targets": [
            {
                "refId": "A",
                "datasource": {"type": datasource_type, "uid": datasource_uid},
                "expr": expr,
            }
        ],
    }


def _logs_panel(panel_id, title, datasource_uid, expr):
    return {
        "id": panel_id,
        "title": title,
        "type": "logs",
        "datasource": {"type": "loki", "uid": datasource_uid},
        "targets": [
            {
                "refId": "A",
                "datasource": {"type": "loki", "uid": datasource_uid},
                "expr": expr,
            }
        ],
    }


def _grafana_dashboard_uid(intent):
    return intent.view_id.replace(":", "-")


def _grafana_dashboard_title(intent):
    if intent.entity_kind == "vm":
        return f"{intent.entity_name} VM Baseline"
    if intent.profile:
        return f"{intent.entity_name} {intent.profile}"
    return intent.entity_name


def _prometheus_regex_escape(value):
    return "".join(f"\\{char}" if char in r"\.^$*+?{}[]|()" else char for char in value)


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
