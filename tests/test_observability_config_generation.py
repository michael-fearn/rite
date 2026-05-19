import unittest
from pathlib import Path

from fortress_inventory.model import InventoryModel
from fortress_inventory.simple_yaml import load_yaml
from fortress_services.deploy import quadlet_deploy_vars


def inventory_model(vms=None, services=None):
    return InventoryModel(
        root=None,
        hosts={},
        vms=vms or {},
        services=services or {},
        datasets={},
        nas_endpoints={},
        templates={},
        template_verification_policy={},
        acceptance_policies={},
        globals={},
    )


class ObservabilityConfigGenerationTests(unittest.TestCase):
    def test_prometheus_config_scrapes_instrumented_vms_by_static_ip(self):
        model = inventory_model(
            vms={
                "observability-vm": {
                    "network": {"interfaces": [{"address": "10.40.0.17/24"}]},
                    "instrumentation": {"enabled": True},
                },
                "media-vm": {
                    "network": {"interfaces": [{"address": "10.50.0.13/24"}]},
                    "instrumentation": {"enabled": True},
                },
            },
            services={"observability": observability_service()},
        )

        prometheus = generated_yaml_file(
            quadlet_deploy_vars(
                model.services["observability"],
                model.vms["observability-vm"],
                model=model,
            ),
            "/srv/services/observability/prometheus-config/prometheus.yml",
        )

        vm_scrapes = scrape_config(prometheus, "fortress-vm-node-exporter")
        self.assertEqual(
            [
                {"targets": ["10.50.0.13:9100"], "labels": {"fortress_vm": "media-vm"}},
                {"targets": ["10.40.0.17:9100"], "labels": {"fortress_vm": "observability-vm"}},
            ],
            vm_scrapes["static_configs"],
        )

    def test_prometheus_config_scrapes_service_metrics_through_published_ports(self):
        model = inventory_model(
            vms={
                "observability-vm": {
                    "network": {"interfaces": [{"address": "10.40.0.17/24"}]},
                    "instrumentation": {"enabled": True},
                },
                "media-vm": {
                    "network": {"interfaces": [{"address": "10.50.0.13/24"}]},
                    "instrumentation": {"enabled": True},
                },
            },
            services={
                "observability": observability_service(),
                "immich": service_with_telemetry_target(
                    target={
                        "name": "metrics",
                        "type": "prometheus_metrics",
                        "published_port": 2283,
                        "path": "/custom-metrics",
                    }
                ),
            },
        )

        prometheus = generated_yaml_file(
            quadlet_deploy_vars(
                model.services["observability"],
                model.vms["observability-vm"],
                model=model,
            ),
            "/srv/services/observability/prometheus-config/prometheus.yml",
        )

        service_metrics = scrape_config(prometheus, "fortress-service-immich-metrics")
        self.assertEqual("http", service_metrics["scheme"])
        self.assertEqual("/custom-metrics", service_metrics["metrics_path"])
        self.assertEqual(
            [
                {
                    "targets": ["10.50.0.13:2283"],
                    "labels": {
                        "fortress_service": "immich",
                        "fortress_telemetry_target": "metrics",
                    },
                }
            ],
            service_metrics["static_configs"],
        )

    def test_prometheus_config_probes_http_targets_with_default_scheme_and_path(self):
        model = inventory_model(
            vms={
                "observability-vm": {
                    "network": {"interfaces": [{"address": "10.40.0.17/24"}]},
                    "instrumentation": {"enabled": True},
                },
                "media-vm": {
                    "network": {"interfaces": [{"address": "10.50.0.13/24"}]},
                    "instrumentation": {"enabled": True},
                },
            },
            services={
                "observability": observability_service(),
                "immich": service_with_telemetry_target(
                    target={
                        "name": "health",
                        "type": "http_probe",
                        "published_port": 2283,
                    }
                ),
            },
        )

        prometheus = generated_yaml_file(
            quadlet_deploy_vars(
                model.services["observability"],
                model.vms["observability-vm"],
                model=model,
            ),
            "/srv/services/observability/prometheus-config/prometheus.yml",
        )

        probes = scrape_config(prometheus, "fortress-service-http-probes")
        self.assertEqual("/probe", probes["metrics_path"])
        self.assertEqual({"module": ["http_2xx"]}, probes["params"])
        self.assertEqual(
            [
                {
                    "targets": ["http://10.50.0.13:2283/"],
                    "labels": {
                        "fortress_service": "immich",
                        "fortress_telemetry_target": "health",
                    },
                }
            ],
            probes["static_configs"],
        )
        self.assertIn(
            {"target_label": "__address__", "replacement": "blackbox:9115"},
            probes["relabel_configs"],
        )

    def test_generated_config_omits_opt_out_vms_and_uses_prometheus_metric_defaults(self):
        model = inventory_model(
            vms={
                "observability-vm": {
                    "network": {"interfaces": [{"address": "10.40.0.17/24"}]},
                    "instrumentation": {"enabled": True},
                },
                "media-vm": {
                    "network": {"interfaces": [{"address": "10.50.0.13/24"}]},
                    "instrumentation": {"enabled": False},
                },
            },
            services={
                "observability": observability_service(),
                "immich": service_with_telemetry_target(
                    target={
                        "name": "metrics",
                        "type": "prometheus_metrics",
                        "published_port": 2283,
                    }
                ),
            },
        )

        prometheus = generated_yaml_file(
            quadlet_deploy_vars(
                model.services["observability"],
                model.vms["observability-vm"],
                model=model,
            ),
            "/srv/services/observability/prometheus-config/prometheus.yml",
        )

        vm_scrapes = scrape_config(prometheus, "fortress-vm-node-exporter")
        self.assertEqual(
            [{"targets": ["10.40.0.17:9100"], "labels": {"fortress_vm": "observability-vm"}}],
            vm_scrapes["static_configs"],
        )

        service_metrics = scrape_config(prometheus, "fortress-service-immich-metrics")
        self.assertEqual("http", service_metrics["scheme"])
        self.assertEqual("/metrics", service_metrics["metrics_path"])

    def test_generated_config_includes_loki_ingestion_endpoint_for_vm_local_alloy(self):
        model = inventory_model(
            vms={
                "observability-vm": {
                    "network": {"interfaces": [{"address": "10.40.0.17/24"}]},
                    "instrumentation": {"enabled": True},
                },
            },
            services={"observability": observability_service()},
        )

        endpoints = generated_yaml_file(
            quadlet_deploy_vars(
                model.services["observability"],
                model.vms["observability-vm"],
                model=model,
            ),
            "/srv/services/observability/generated-endpoints.yml",
        )

        self.assertEqual(
            {
                "loki": {
                    "host": "10.40.0.17",
                    "port": 3100,
                    "push_url": "http://10.40.0.17:3100/loki/api/v1/push",
                }
            },
            endpoints,
        )


def observability_service():
    return {
        "name": "observability",
        "service_data_owner": {"uid": 1000, "gid": 1000},
        "backend": {"vm": "observability-vm", "port": 3000},
        "deploy": {
            "type": "quadlet",
            "containers": [
                {"name": "prometheus", "image": "docker.io/prom/prometheus:v3.4.0"},
                {"name": "blackbox", "image": "docker.io/prom/blackbox-exporter:v0.26.0"},
                {
                    "name": "loki",
                    "image": "docker.io/grafana/loki:3.5.0",
                    "published_ports": [{"container": 3100, "host": 3100, "bind": "0.0.0.0"}],
                },
            ],
        },
    }


def service_with_telemetry_target(target):
    return {
        "name": "immich",
        "backend": {"vm": "media-vm", "port": 2283},
        "instrumentation": {"telemetry_targets": [target]},
        "deploy": {
            "type": "quadlet",
            "containers": [
                {
                    "name": "server",
                    "image": "ghcr.io/immich-app/immich-server:v1.120.0",
                    "published_ports": [{"container": 2283, "host": 2283, "bind": "0.0.0.0"}],
                }
            ],
        },
    }


def generated_yaml_file(deploy_vars, path):
    matches = [
        file
        for file in deploy_vars["fortress_service_data_files"]
        if file["path"] == path
    ]
    if len(matches) != 1:
        raise AssertionError(f"expected one generated file at {path}, got {matches}")
    return load_yaml_from_text(matches[0]["content"])


def load_yaml_from_text(content):
    from tempfile import NamedTemporaryFile

    with NamedTemporaryFile("w+", encoding="utf-8") as file:
        file.write(content)
        file.flush()
        return load_yaml(Path(file.name))


def scrape_config(prometheus, job_name):
    matches = [
        config
        for config in prometheus["scrape_configs"]
        if config["job_name"] == job_name
    ]
    if len(matches) != 1:
        raise AssertionError(f"expected one scrape_config named {job_name}, got {matches}")
    return matches[0]
