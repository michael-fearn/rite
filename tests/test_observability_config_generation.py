import json
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_generated_config_omits_live_absent_vms_excluded_by_convergence(self):
        model = inventory_model(
            vms={
                "observability-vm": {
                    "network": {"interfaces": [{"address": "10.40.0.17/24"}]},
                    "instrumentation": {"enabled": True},
                },
                "stale-vm": {
                    "network": {"interfaces": [{"address": "10.50.0.99/24"}]},
                    "instrumentation": {"enabled": True},
                },
            },
            services={"observability": observability_service()},
        )

        with patch.dict("os.environ", {"FORTRESS_OBSERVABILITY_EXCLUDED_VMS": "stale-vm"}):
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

    def test_generates_replaceable_grafana_provisioning_owned_by_observability_service(self):
        model = inventory_model(
            vms={
                "observability-vm": {
                    "network": {"interfaces": [{"address": "10.40.0.17/24"}]},
                    "instrumentation": {"enabled": True},
                },
            },
            services={"observability": observability_service()},
        )

        deploy_vars = quadlet_deploy_vars(
            model.services["observability"],
            model.vms["observability-vm"],
            model=model,
        )

        provider = generated_yaml_file(
            deploy_vars,
            "/srv/services/observability/grafana-provisioning/dashboards/fortress-generated.yml",
        )
        self.assertEqual(1, provider["apiVersion"])
        self.assertEqual(
            [
                {
                    "name": "fortress-generated-observability-views",
                    "orgId": 1,
                    "folder": "Rite Generated Observability",
                    "folderUid": "fortress-generated-observability",
                    "type": "file",
                    "disableDeletion": False,
                    "editable": False,
                    "allowUiUpdates": False,
                    "options": {
                        "path": "/var/lib/grafana/dashboards/fortress-generated",
                    },
                }
            ],
            provider["providers"],
        )
        for path in (
            "/srv/services/observability/grafana-provisioning/dashboards/fortress-generated.yml",
            "/srv/services/observability/grafana-dashboards/generated/vm-observability-vm-vm_baseline.json",
        ):
            artifact = generated_file(deploy_vars, path)
            self.assertEqual(1000, artifact["uid"])
            self.assertEqual(1000, artifact["gid"])
            self.assertTrue(artifact["force"])

    def test_generates_dashboard_file_for_each_current_observability_view_intent(self):
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
                "immich": {
                    **service_with_telemetry_target(
                        target={
                            "name": "metrics",
                            "type": "prometheus_metrics",
                            "published_port": 2283,
                        }
                    ),
                    "instrumentation": {
                        "telemetry_targets": [
                            {
                                "name": "metrics",
                                "type": "prometheus_metrics",
                                "published_port": 2283,
                            }
                        ],
                        "observability_views": [{"profile": "prometheus_generic"}],
                    },
                },
            },
        )

        deploy_vars = quadlet_deploy_vars(
            model.services["observability"],
            model.vms["observability-vm"],
            model=model,
        )

        baseline = json.loads(
            generated_file(
                deploy_vars,
                "/srv/services/observability/grafana-dashboards/generated/vm-media-vm-vm_baseline.json",
            )["content"]
        )
        service = json.loads(
            generated_file(
                deploy_vars,
                "/srv/services/observability/grafana-dashboards/generated/service-immich-prometheus_generic.json",
            )["content"]
        )
        self.assertEqual("vm-media-vm-vm_baseline", baseline["uid"])
        self.assertEqual("service-immich-prometheus_generic", service["uid"])
        self.assertEqual("media-vm VM Baseline", baseline["title"])
        self.assertNotEqual([], baseline["panels"])
        self.assertNotEqual([], service["panels"])

    def test_generates_vm_baseline_dashboard_for_enabled_vm_instrumentation(self):
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

        dashboard = generated_dashboard(
            quadlet_deploy_vars(
                model.services["observability"],
                model.vms["observability-vm"],
                model=model,
            ),
            "vm-media-vm-vm_baseline",
        )

        self.assertEqual("vm-media-vm-vm_baseline", dashboard["uid"])
        self.assertEqual("media-vm VM Baseline", dashboard["title"])
        self.assertEqual(["CPU", "Memory", "System Logs"], [panel["title"] for panel in dashboard["panels"]])
        for panel in dashboard["panels"]:
            self.assertIn('fortress_vm="media-vm"', panel_target_exprs(panel))

    def test_vm_baseline_dashboard_omits_vms_opted_out_of_vm_instrumentation(self):
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
            services={"observability": observability_service()},
        )

        deploy_vars = quadlet_deploy_vars(
            model.services["observability"],
            model.vms["observability-vm"],
            model=model,
        )

        self.assertEqual(["vm-observability-vm-vm_baseline"], generated_dashboard_uids(deploy_vars))

    def test_vm_baseline_dashboard_uses_provisioning_safe_prometheus_and_loki_datasource_variables(self):
        model = inventory_model(
            vms={
                "observability-vm": {
                    "network": {"interfaces": [{"address": "10.40.0.17/24"}]},
                    "instrumentation": {"enabled": True},
                },
            },
            services={"observability": observability_service()},
        )

        dashboard = generated_dashboard(
            quadlet_deploy_vars(
                model.services["observability"],
                model.vms["observability-vm"],
                model=model,
            ),
            "vm-observability-vm-vm_baseline",
        )

        self.assertEqual(
            [
                {"name": "DS_LOKI", "query": "loki", "type": "datasource"},
                {"name": "DS_PROMETHEUS", "query": "prometheus", "type": "datasource"},
            ],
            sorted(
                (
                    {
                        "name": variable["name"],
                        "query": variable["query"],
                        "type": variable["type"],
                    }
                    for variable in dashboard["templating"]["list"]
                ),
                key=lambda variable: variable["name"],
            ),
        )
        self.assertEqual(
            [
                ("CPU", "prometheus", "${DS_PROMETHEUS}"),
                ("Memory", "prometheus", "${DS_PROMETHEUS}"),
                ("System Logs", "loki", "${DS_LOKI}"),
            ],
            [
                (panel["title"], panel["datasource"]["type"], panel["datasource"]["uid"])
                for panel in dashboard["panels"]
            ],
        )

    def test_prometheus_generic_service_dashboard_includes_requested_service_metrics(self):
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
                "immich": service_with_observability_view(
                    telemetry_targets=[
                        {
                            "name": "metrics",
                            "type": "prometheus_metrics",
                            "published_port": 2283,
                        }
                    ]
                ),
            },
        )

        dashboard = generated_dashboard(
            quadlet_deploy_vars(
                model.services["observability"],
                model.vms["observability-vm"],
                model=model,
            ),
            "service-immich-prometheus_generic",
        )

        self.assertEqual("service-immich-prometheus_generic", dashboard["uid"])
        self.assertEqual("immich prometheus_generic", dashboard["title"])
        self.assertEqual(
            ["Service Request Rate", "Service Error Rate"],
            [panel["title"] for panel in dashboard["panels"]],
        )
        for panel in dashboard["panels"]:
            self.assertEqual("prometheus", panel["datasource"]["type"])
            self.assertEqual("${DS_PROMETHEUS}", panel["datasource"]["uid"])
            self.assertIn('fortress_service="immich"', panel_target_exprs(panel))
            self.assertIn('fortress_telemetry_target=~"metrics"', panel_target_exprs(panel))

    def test_prometheus_generic_service_dashboard_is_one_view_per_service_with_multiple_targets(self):
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
                "immich": service_with_observability_view(
                    telemetry_targets=[
                        {
                            "name": "api",
                            "type": "prometheus_metrics",
                            "published_port": 2283,
                        },
                        {
                            "name": "machine-learning",
                            "type": "prometheus_metrics",
                            "published_port": 2283,
                        },
                    ]
                ),
            },
        )

        deploy_vars = quadlet_deploy_vars(
            model.services["observability"],
            model.vms["observability-vm"],
            model=model,
        )
        dashboard = generated_dashboard(deploy_vars, "service-immich-prometheus_generic")

        self.assertEqual(
            ["service-immich-prometheus_generic"],
            [
                uid
                for uid in generated_dashboard_uids(deploy_vars)
                if uid.startswith("service-immich-")
            ],
        )
        for panel in dashboard["panels"]:
            self.assertIn(
                'fortress_telemetry_target=~"api|machine-learning"',
                panel_target_exprs(panel),
            )

    def test_prometheus_generic_service_dashboard_is_not_implicit_for_services_with_metrics(self):
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
                    }
                ),
            },
        )

        deploy_vars = quadlet_deploy_vars(
            model.services["observability"],
            model.vms["observability-vm"],
            model=model,
        )

        self.assertNotIn("service-immich-prometheus_generic", generated_dashboard_uids(deploy_vars))

    def test_prometheus_generic_service_dashboard_identity_uses_service_identity_and_profile(self):
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
                "immich": {
                    **service_with_observability_view(
                        telemetry_targets=[
                            {
                                "name": "metrics",
                                "type": "prometheus_metrics",
                                "published_port": 2283,
                            }
                        ]
                    ),
                    "name": "Immich Photos",
                },
            },
        )

        deploy_vars = quadlet_deploy_vars(
            model.services["observability"],
            model.vms["observability-vm"],
            model=model,
        )

        self.assertIsNotNone(
            generated_file(
                deploy_vars,
                "/srv/services/observability/grafana-dashboards/generated/service-immich-prometheus_generic.json",
            )
        )
        dashboard = generated_dashboard(deploy_vars, "service-immich-prometheus_generic")
        self.assertEqual("service-immich-prometheus_generic", dashboard["uid"])

    def test_generated_grafana_dashboard_directory_is_reconciled_on_observability_deploy(self):
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
                "immich": service_with_observability_view(
                    [{"name": "metrics", "type": "prometheus_metrics", "published_port": 2283}]
                ),
            },
        )

        deploy_vars = quadlet_deploy_vars(
            model.services["observability"],
            model.vms["observability-vm"],
            model=model,
        )

        self.assertEqual(
            ["/srv/services/observability/grafana-dashboards/generated"],
            deploy_vars["fortress_service_data_reconcile_directories"],
        )
        self.assertEqual(
            ["service-immich-prometheus_generic", "vm-media-vm-vm_baseline", "vm-observability-vm-vm_baseline"],
            generated_dashboard_uids(deploy_vars),
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


def service_with_observability_view(telemetry_targets):
    return {
        **service_with_telemetry_target(telemetry_targets[0]),
        "instrumentation": {
            "telemetry_targets": telemetry_targets,
            "observability_views": [{"profile": "prometheus_generic"}],
        },
    }


def generated_yaml_file(deploy_vars, path):
    return load_yaml_from_text(generated_file(deploy_vars, path)["content"])


def generated_dashboard(deploy_vars, uid):
    return json.loads(
        generated_file(
            deploy_vars,
            f"/srv/services/observability/grafana-dashboards/generated/{uid}.json",
        )["content"]
    )


def generated_dashboard_uids(deploy_vars):
    return sorted(
        json.loads(file["content"])["uid"]
        for file in deploy_vars["fortress_service_data_files"]
        if file["path"].startswith("/srv/services/observability/grafana-dashboards/generated/")
    )


def generated_file(deploy_vars, path):
    matches = [
        file
        for file in deploy_vars["fortress_service_data_files"]
        if file["path"] == path
    ]
    if len(matches) != 1:
        raise AssertionError(f"expected one generated file at {path}, got {matches}")
    return matches[0]


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


def panel_target_exprs(panel):
    return "\n".join(target["expr"] for target in panel["targets"])
