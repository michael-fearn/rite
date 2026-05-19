import unittest
from dataclasses import dataclass

from fortress_inventory.service_runtime_intent import analyze_service_runtime_intent


@dataclass(frozen=True)
class InventoryStub:
    vms: dict
    services: dict


class ServiceRuntimeIntentTests(unittest.TestCase):
    def test_fleet_analysis_resolves_backend_and_normalized_published_port_facts(self):
        model = InventoryStub(
            vms={"media01": {}},
            services={
                "immich": {
                    "name": "immich",
                    "backend": {"vm": "media01", "port": 2283},
                    "deploy": {
                        "type": "quadlet",
                        "containers": [
                            {
                                "name": "server",
                                "published_ports": [
                                    {
                                        "container": 2283,
                                        "ingress": True,
                                    }
                                ],
                            }
                        ],
                    },
                }
            },
        )

        intent = analyze_service_runtime_intent(model)

        self.assertEqual((), intent.diagnostics)
        self.assertEqual(
            [("immich", "media01", 2283)],
            [
                (backend.service_name, backend.vm_name, backend.port)
                for backend in intent.backends
            ],
        )
        self.assertEqual(
            [("immich", "media01", "server", 0, 2283, 2283, "127.0.0.1", ("tcp",), True)],
            [
                (
                    published_port.service_name,
                    published_port.vm_name,
                    published_port.container_name,
                    published_port.container_index,
                    published_port.host_port,
                    published_port.container_port,
                    published_port.bind,
                    published_port.protocols,
                    published_port.ingress,
                )
                for published_port in intent.published_ports
            ],
        )

    def test_fleet_analysis_resolves_service_telemetry_target_facts(self):
        model = InventoryStub(
            vms={"media01": {}},
            services={
                "immich": {
                    "backend": {"vm": "media01", "port": 2283},
                    "instrumentation": {
                        "telemetry_targets": [
                            {
                                "name": "metrics",
                                "type": "prometheus_metrics",
                                "published_port": 2283,
                            },
                            {
                                "name": "health",
                                "type": "http_probe",
                                "published_port": 2283,
                                "scheme": "https",
                                "path": "/healthz",
                            },
                        ]
                    },
                    "deploy": {
                        "type": "quadlet",
                        "containers": [
                            {
                                "name": "server",
                                "published_ports": [
                                    {"container": 2283, "bind": "0.0.0.0"},
                                ],
                            }
                        ],
                    },
                }
            },
        )

        intent = analyze_service_runtime_intent(model)

        self.assertEqual((), intent.diagnostics)
        self.assertEqual(
            [
                ("immich", "media01", "metrics", "prometheus_metrics", 2283, "http", "/metrics"),
                ("immich", "media01", "health", "http_probe", 2283, "https", "/healthz"),
            ],
            [
                (
                    target.service_name,
                    target.vm_name,
                    target.name,
                    target.target_type,
                    target.published_port,
                    target.scheme,
                    target.path,
                )
                for target in intent.telemetry_targets
            ],
        )

    def test_fleet_analysis_diagnoses_backend_port_collisions_and_keeps_facts(self):
        model = InventoryStub(
            vms={"media01": {}},
            services={
                "immich": {
                    "backend": {"vm": "media01", "port": 2283},
                },
                "photos": {
                    "backend": {"vm": "media01", "port": 2283},
                },
            },
        )

        intent = analyze_service_runtime_intent(model)

        self.assertEqual(
            [("immich", "media01", 2283), ("photos", "media01", 2283)],
            [(backend.service_name, backend.vm_name, backend.port) for backend in intent.backends],
        )
        self.assertEqual(["backend_port_collision"], [diagnostic.code for diagnostic in intent.diagnostics])
        self.assertEqual("inventory/services/photos.yaml.backend.port", intent.diagnostics[0].path)

    def test_fleet_analysis_diagnoses_published_port_collisions_per_protocol(self):
        model = InventoryStub(
            vms={"media01": {}},
            services={
                "dns-primary": {
                    "backend": {"vm": "media01", "port": 53},
                    "deploy": {
                        "type": "quadlet",
                        "containers": [
                            {
                                "name": "pihole",
                                "published_ports": [
                                    {"container": 53, "protocol": "tcp_udp"},
                                ],
                            }
                        ],
                    },
                },
                "dns-shadow": {
                    "backend": {"vm": "media01", "port": 8053},
                    "deploy": {
                        "type": "quadlet",
                        "containers": [
                            {
                                "name": "shadow",
                                "published_ports": [
                                    {"host": 53, "container": 8053, "protocol": "udp"},
                                ],
                            }
                        ],
                    },
                },
            },
        )

        intent = analyze_service_runtime_intent(model)

        self.assertEqual(["published_port_collision"], [diagnostic.code for diagnostic in intent.diagnostics])
        self.assertEqual(
            "inventory/services/dns-shadow.yaml.deploy.containers[0].published_ports[0].host",
            intent.diagnostics[0].path,
        )
        self.assertIn("UDP port 53", intent.diagnostics[0].message)

    def test_fleet_analysis_diagnoses_ingress_backend_port_match_count(self):
        model = InventoryStub(
            vms={"media01": {}},
            services={
                "immich": {
                    "backend": {"vm": "media01", "port": 2283},
                    "ingress": {"enabled": True},
                    "deploy": {
                        "type": "quadlet",
                        "containers": [
                            {
                                "name": "server",
                                "published_ports": [
                                    {"container": 2283, "protocol": "udp", "ingress": True},
                                ],
                            }
                        ],
                    },
                },
                "photos": {
                    "backend": {"vm": "media01", "port": 8080},
                    "ingress": {"enabled": True},
                    "deploy": {
                        "type": "quadlet",
                        "containers": [
                            {
                                "name": "web",
                                "published_ports": [
                                    {"container": 8080, "ingress": True},
                                    {"host": 8080, "container": 3000, "protocol": "tcp_udp", "ingress": True},
                                ],
                            }
                        ],
                    },
                },
            },
        )

        intent = analyze_service_runtime_intent(model)

        ingress_diagnostics = [
            diagnostic
            for diagnostic in intent.diagnostics
            if diagnostic.code in {"invalid_ingress_published_port", "missing_ingress_published_port"}
        ]
        self.assertEqual(
            ["invalid_ingress_published_port", "missing_ingress_published_port", "invalid_ingress_published_port"],
            [diagnostic.code for diagnostic in ingress_diagnostics],
        )
        self.assertEqual(
            ["inventory/services/immich.yaml.backend.port", "inventory/services/photos.yaml.backend.port"],
            [
                diagnostic.path
                for diagnostic in ingress_diagnostics
                if diagnostic.code == "invalid_ingress_published_port"
            ],
        )
