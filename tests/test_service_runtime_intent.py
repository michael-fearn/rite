import unittest
from dataclasses import dataclass

from fortress_inventory.service_runtime_intent import (
    analyze_service_runtime_intent,
    service_runtime_intent_for_service,
)


@dataclass(frozen=True)
class InventoryStub:
    vms: dict
    services: dict


class ServiceRuntimeIntentTests(unittest.TestCase):
    def test_per_service_view_matches_filtering_the_fleet_wide_service_runtime_intent(self):
        model = InventoryStub(
            vms={
                "media01": {
                    "mounts": [
                        {
                            "name": "media",
                            "dataset": "media",
                            "mount_point": "/mnt/nas/media",
                            "access": "read_write",
                        }
                    ]
                },
                "ingress01": {},
            },
            services={
                "jellyfin": {
                    "backend": {"vm": "media01", "port": 8096},
                    "deploy": {
                        "type": "quadlet",
                        "containers": [
                            {
                                "name": "server",
                                "published_ports": [{"container": 8096, "bind": "0.0.0.0"}],
                                "volumes": [
                                    {
                                        "mount": "media",
                                        "source": "movies",
                                        "container": "/movies",
                                    },
                                    {
                                        "mount": "missing-media",
                                        "source": "/",
                                        "container": "/missing",
                                    },
                                ],
                                "secrets": [
                                    {
                                        "secret": "secrets.admin_password",
                                        "env": "JELLYFIN_ADMIN_PASSWORD_FILE",
                                    }
                                ],
                            }
                        ],
                    },
                    "instrumentation": {
                        "telemetry_targets": [
                            {
                                "name": "metrics",
                                "type": "prometheus_metrics",
                                "published_port": 8096,
                            }
                        ]
                    },
                },
                "internal-ingress": {
                    "backend": {"vm": "ingress01", "port": 443},
                    "deploy": {
                        "type": "native",
                        "package": "caddy",
                        "service_name": "caddy",
                        "environment_secrets": [
                            {
                                "secret": "secrets.cloudflare_api_token",
                                "env": "CLOUDFLARE_API_TOKEN",
                            }
                        ],
                    },
                },
            },
        )

        fleet_intent = analyze_service_runtime_intent(model)
        service_intent = service_runtime_intent_for_service(fleet_intent, "jellyfin")

        self.assertEqual(
            tuple(fact for fact in fleet_intent.backends if fact.service_name == "jellyfin"),
            service_intent.backends,
        )
        self.assertEqual(
            tuple(fact for fact in fleet_intent.published_ports if fact.service_name == "jellyfin"),
            service_intent.published_ports,
        )
        self.assertEqual(
            tuple(fact for fact in fleet_intent.telemetry_targets if fact.service_name == "jellyfin"),
            service_intent.telemetry_targets,
        )
        self.assertEqual(
            tuple(fact for fact in fleet_intent.service_secrets if fact.service_name == "jellyfin"),
            service_intent.service_secrets,
        )
        self.assertEqual(
            tuple(fact for fact in fleet_intent.share_backed_volumes if fact.service_name == "jellyfin"),
            service_intent.share_backed_volumes,
        )
        self.assertEqual((), service_intent.native_environment_secrets)
        self.assertEqual(
            tuple(
                diagnostic
                for diagnostic in fleet_intent.diagnostics
                if diagnostic.path.startswith("inventory/services/jellyfin.yaml")
            ),
            service_intent.diagnostics,
        )

    def test_runtime_intent_compatibility_adapter_exports_per_service_view(self):
        from fortress_services.runtime_intent import service_runtime_intent_for_service as adapter_view

        model = InventoryStub(
            vms={"media01": {}},
            services={
                "jellyfin": {"backend": {"vm": "media01", "port": 8096}},
                "photos": {"backend": {"vm": "media01", "port": 8080}},
            },
        )

        fleet_intent = analyze_service_runtime_intent(model)

        self.assertEqual(
            [("photos", "media01", 8080)],
            [
                (backend.service_name, backend.vm_name, backend.port)
                for backend in adapter_view(fleet_intent, "photos").backends
            ],
        )

    def test_fleet_analysis_resolves_share_backed_volume_facts(self):
        model = InventoryStub(
            vms={
                "media01": {
                    "mounts": [
                        {
                            "name": "media",
                            "dataset": "media",
                            "protocol": "nfs",
                            "mount_point": "/mnt/nas/media",
                            "access": "read_write",
                        },
                        {
                            "name": "nfs-demo",
                            "dataset": "demo",
                            "protocol": "nfs",
                            "mount_point": "/mnt/nfs-demo",
                            "access": "read_write",
                        },
                    ]
                }
            },
            services={
                "jellyfin": {
                    "backend": {"vm": "media01", "port": 8096},
                    "deploy": {
                        "type": "quadlet",
                        "containers": [
                            {
                                "name": "server",
                                "volumes": [
                                    {
                                        "mount": "media",
                                        "source": "photos",
                                        "container": "/photos",
                                        "access": "read_only",
                                    },
                                    {
                                        "mount": "nfs-demo",
                                        "source": "/",
                                        "container": "/mnt/shared",
                                    },
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
                (
                    "jellyfin",
                    "media01",
                    "server",
                    0,
                    0,
                    "media",
                    "media",
                    "/mnt/nas/media",
                    "/mnt/nas/media/photos",
                    "/photos",
                    "read_only",
                    "mnt-nas-media.mount",
                ),
                (
                    "jellyfin",
                    "media01",
                    "server",
                    0,
                    1,
                    "nfs-demo",
                    "demo",
                    "/mnt/nfs-demo",
                    "/mnt/nfs-demo",
                    "/mnt/shared",
                    "read_write",
                    "mnt-nfs\\x2ddemo.mount",
                ),
            ],
            [
                (
                    volume.service_name,
                    volume.vm_name,
                    volume.container_name,
                    volume.container_index,
                    volume.volume_index,
                    volume.mount_name,
                    volume.dataset_name,
                    volume.vm_mount_path,
                    volume.resolved_source_path,
                    volume.container_path,
                    volume.access,
                    volume.required_mount_unit,
                )
                for volume in intent.share_backed_volumes
            ],
        )

    def test_fleet_analysis_diagnoses_missing_share_backed_volume_mount_and_keeps_partial_facts(self):
        model = InventoryStub(
            vms={
                "media01": {
                    "mounts": [
                        {
                            "name": "media",
                            "dataset": "media",
                            "protocol": "nfs",
                            "mount_point": "/mnt/nas/media",
                            "access": "read_write",
                        }
                    ]
                }
            },
            services={
                "jellyfin": {
                    "backend": {"vm": "media01", "port": 8096},
                    "deploy": {
                        "type": "quadlet",
                        "containers": [
                            {
                                "name": "server",
                                "volumes": [
                                    {
                                        "mount": "media",
                                        "source": "movies",
                                        "container": "/movies",
                                    },
                                    {
                                        "mount": "missing-media",
                                        "source": "/",
                                        "container": "/missing",
                                    },
                                ],
                            }
                        ],
                    },
                }
            },
        )

        intent = analyze_service_runtime_intent(model)

        self.assertEqual(["missing_service_volume_mount"], [d.code for d in intent.diagnostics])
        self.assertEqual(
            "inventory/services/jellyfin.yaml.deploy.containers[0].volumes[1].mount",
            intent.diagnostics[0].path,
        )
        self.assertEqual(
            [("media", "/mnt/nas/media/movies")],
            [(volume.mount_name, volume.resolved_source_path) for volume in intent.share_backed_volumes],
        )

    def test_fleet_analysis_diagnoses_unsafe_share_backed_volume_sources(self):
        for source in ("/mnt/nas/media", "../photos", "photos/../secrets"):
            with self.subTest(source=source):
                model = InventoryStub(
                    vms={
                        "media01": {
                            "mounts": [
                                {
                                    "name": "media",
                                    "dataset": "media",
                                    "protocol": "nfs",
                                    "mount_point": "/mnt/nas/media",
                                    "access": "read_write",
                                }
                            ]
                        }
                    },
                    services={
                        "jellyfin": {
                            "backend": {"vm": "media01", "port": 8096},
                            "deploy": {
                                "type": "quadlet",
                                "containers": [
                                    {
                                        "name": "server",
                                        "volumes": [
                                            {
                                                "mount": "media",
                                                "source": source,
                                                "container": "/photos",
                                                "access": "read_only",
                                            }
                                        ],
                                    }
                                ],
                            },
                        }
                    },
                )

                intent = analyze_service_runtime_intent(model)

                self.assertEqual(["unsafe_service_volume_source"], [d.code for d in intent.diagnostics])
                self.assertEqual(
                    "inventory/services/jellyfin.yaml.deploy.containers[0].volumes[0].source",
                    intent.diagnostics[0].path,
                )

    def test_fleet_analysis_diagnoses_share_backed_volume_access_widening(self):
        model = InventoryStub(
            vms={
                "media01": {
                    "mounts": [
                        {
                            "name": "media",
                            "dataset": "media",
                            "protocol": "nfs",
                            "mount_point": "/mnt/nas/media",
                            "access": "read_only",
                        }
                    ]
                }
            },
            services={
                "jellyfin": {
                    "backend": {"vm": "media01", "port": 8096},
                    "deploy": {
                        "type": "quadlet",
                        "containers": [
                            {
                                "name": "server",
                                "volumes": [
                                    {
                                        "mount": "media",
                                        "source": "photos",
                                        "container": "/photos",
                                        "access": "read_write",
                                    }
                                ],
                            }
                        ],
                    },
                }
            },
        )

        intent = analyze_service_runtime_intent(model)

        self.assertEqual(["service_volume_widens_mount_access"], [d.code for d in intent.diagnostics])
        self.assertEqual(
            "inventory/services/jellyfin.yaml.deploy.containers[0].volumes[0].access",
            intent.diagnostics[0].path,
        )
        self.assertEqual("read_write", intent.share_backed_volumes[0].access)

    def test_fleet_analysis_resolves_service_owned_volume_facts(self):
        model = InventoryStub(
            vms={
                "media01": {
                    "mounts": [
                        {
                            "name": "media",
                            "dataset": "media",
                            "mount_point": "/mnt/nas/media",
                            "access": "read_write",
                        }
                    ]
                }
            },
            services={
                "immich": {
                    "name": "immich",
                    "service_data_owner": {"uid": 1000, "gid": 1000},
                    "backend": {"vm": "media01", "port": 2283},
                    "deploy": {
                        "type": "quadlet",
                        "containers": [
                            {
                                "name": "server",
                                "volumes": [
                                    {
                                        "service_path": "upload",
                                        "container": "/usr/src/app/upload",
                                        "access": "read_only",
                                    },
                                    {
                                        "mount": "media",
                                        "source": "photos",
                                        "container": "/photos",
                                    },
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
                (
                    "immich",
                    "media01",
                    "server",
                    0,
                    0,
                    "upload",
                    "/srv/services/immich/upload",
                    "/usr/src/app/upload",
                    "ro",
                    1000,
                    1000,
                )
            ],
            [
                (
                    volume.service_name,
                    volume.vm_name,
                    volume.container_name,
                    volume.container_index,
                    volume.volume_index,
                    volume.service_path,
                    volume.vm_path,
                    volume.container_path,
                    volume.access_mode,
                    volume.uid,
                    volume.gid,
                )
                for volume in intent.service_owned_volumes
            ],
        )

    def test_fleet_analysis_deduplicates_service_data_directory_facts(self):
        model = InventoryStub(
            vms={"media01": {}},
            services={
                "immich": {
                    "name": "immich",
                    "service_data_owner": {"uid": 1000, "gid": 1000},
                    "backend": {"vm": "media01", "port": 2283},
                    "deploy": {
                        "type": "quadlet",
                        "containers": [
                            {
                                "name": "server",
                                "volumes": [
                                    {"service_path": "upload", "container": "/data"},
                                    {"service_path": "upload", "container": "/backup"},
                                    {"mount": "media", "source": "photos", "container": "/photos"},
                                ],
                            }
                        ],
                    },
                }
            },
        )

        intent = analyze_service_runtime_intent(model)

        self.assertEqual(
            [("immich", "media01", "/srv/services/immich/upload", 1000, 1000)],
            [
                (
                    directory.service_name,
                    directory.vm_name,
                    directory.path,
                    directory.uid,
                    directory.gid,
                )
                for directory in intent.service_data_directories
            ],
        )

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

    def test_fleet_analysis_resolves_quadlet_service_secret_facts(self):
        model = InventoryStub(
            vms={"media01": {}},
            services={
                "paperless": {
                    "backend": {"vm": "media01", "port": 8000},
                    "deploy": {
                        "type": "quadlet",
                        "containers": [
                            {
                                "name": "web",
                                "secrets": [
                                    {
                                        "secret": "secrets.admin_password",
                                        "env": "PAPERLESS_ADMIN_PASSWORD_FILE",
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
            [
                (
                    "paperless",
                    "web",
                    0,
                    0,
                    "admin_password",
                    "fortress_paperless_admin_password",
                    "PAPERLESS_ADMIN_PASSWORD_FILE",
                    '["secrets"]["admin_password"]["value"]',
                    "file_path",
                )
            ],
            [
                (
                    secret.service_name,
                    secret.container_name,
                    secret.container_index,
                    secret.secret_index,
                    secret.secret_key,
                    secret.podman_name,
                    secret.env,
                    secret.sops_extract,
                    secret.env_value_mode,
                )
                for secret in intent.service_secrets
            ],
        )

    def test_fleet_analysis_resolves_native_service_environment_secret_facts(self):
        model = InventoryStub(
            vms={"ingress01": {}},
            services={
                "internal-ingress": {
                    "backend": {"vm": "ingress01", "port": 443},
                    "deploy": {
                        "type": "native",
                        "package": "caddy",
                        "service_name": "caddy",
                        "environment_secrets": [
                            {
                                "secret": "secrets.cloudflare_api_token",
                                "env": "CLOUDFLARE_API_TOKEN",
                            }
                        ],
                    },
                }
            },
        )

        intent = analyze_service_runtime_intent(model)

        self.assertEqual((), intent.diagnostics)
        self.assertEqual((), intent.service_secrets)
        self.assertEqual(
            [
                (
                    "internal-ingress",
                    0,
                    "cloudflare_api_token",
                    "CLOUDFLARE_API_TOKEN",
                    '["secrets"]["cloudflare_api_token"]["value"]',
                )
            ],
            [
                (
                    secret.service_name,
                    secret.secret_index,
                    secret.secret_key,
                    secret.env,
                    secret.sops_extract,
                )
                for secret in intent.native_environment_secrets
            ],
        )

    def test_fleet_analysis_diagnoses_invalid_native_secret_refs_and_keeps_valid_facts(self):
        model = InventoryStub(
            vms={"ingress01": {}},
            services={
                "internal-ingress": {
                    "backend": {"vm": "ingress01", "port": 443},
                    "deploy": {
                        "type": "native",
                        "package": "caddy",
                        "service_name": "caddy",
                        "environment_secrets": [
                            {
                                "secret": "shared.cloudflare_api_token",
                                "env": "CLOUDFLARE_API_TOKEN",
                            },
                            {
                                "secret": "secrets.dns_api_token",
                                "env": "DNS_API_TOKEN",
                            },
                        ],
                    },
                }
            },
        )

        intent = analyze_service_runtime_intent(model)

        self.assertEqual(
            ["native_environment_secret_reference_not_sibling_sops_secret"],
            [diagnostic.code for diagnostic in intent.diagnostics],
        )
        self.assertEqual(
            "inventory/services/internal-ingress.yaml.deploy.environment_secrets[0].secret",
            intent.diagnostics[0].path,
        )
        self.assertEqual(
            [("dns_api_token", "DNS_API_TOKEN", '["secrets"]["dns_api_token"]["value"]')],
            [
                (secret.secret_key, secret.env, secret.sops_extract)
                for secret in intent.native_environment_secrets
            ],
        )

    def test_fleet_analysis_represents_service_secret_name_env_value_mode(self):
        model = InventoryStub(
            vms={"media01": {}},
            services={
                "dns-primary": {
                    "backend": {"vm": "media01", "port": 8080},
                    "deploy": {
                        "type": "quadlet",
                        "containers": [
                            {
                                "name": "pihole",
                                "secrets": [
                                    {
                                        "secret": "secrets.web_api_password",
                                        "env": "PIHOLE_WEBPASSWORD",
                                        "env_value": "secret_name",
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
        self.assertEqual("secret_name", intent.service_secrets[0].env_value_mode)

    def test_fleet_analysis_diagnoses_invalid_service_secret_reference_and_keeps_partial_fact(self):
        model = InventoryStub(
            vms={"media01": {}},
            services={
                "paperless": {
                    "backend": {"vm": "media01", "port": 8000},
                    "deploy": {
                        "type": "quadlet",
                        "containers": [
                            {
                                "name": "web",
                                "secrets": [
                                    {
                                        "secret": "admin_password",
                                        "env": "PAPERLESS_ADMIN_PASSWORD_FILE",
                                    }
                                ],
                            }
                        ],
                    },
                }
            },
        )

        intent = analyze_service_runtime_intent(model)

        self.assertEqual(["service_secret_reference_not_sibling_sops_secret"], [d.code for d in intent.diagnostics])
        self.assertEqual(
            "inventory/services/paperless.yaml.deploy.containers[0].secrets[0].secret",
            intent.diagnostics[0].path,
        )
        self.assertEqual("admin_password", intent.service_secrets[0].secret_key)

    def test_fleet_analysis_diagnoses_file_path_service_secret_env_without_file_suffix(self):
        model = InventoryStub(
            vms={"media01": {}},
            services={
                "paperless": {
                    "backend": {"vm": "media01", "port": 8000},
                    "deploy": {
                        "type": "quadlet",
                        "containers": [
                            {
                                "name": "web",
                                "secrets": [
                                    {
                                        "secret": "secrets.admin_password",
                                        "env": "PAPERLESS_ADMIN_PASSWORD",
                                    },
                                    {
                                        "secret": "secrets.api_token",
                                        "env": "PAPERLESS_API_TOKEN",
                                        "env_value": "secret_name",
                                    },
                                ],
                            }
                        ],
                    },
                }
            },
        )

        intent = analyze_service_runtime_intent(model)

        self.assertEqual(["service_secret_env_not_file"], [d.code for d in intent.diagnostics])
        self.assertEqual(
            "inventory/services/paperless.yaml.deploy.containers[0].secrets[0].env",
            intent.diagnostics[0].path,
        )
