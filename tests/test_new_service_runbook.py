import unittest
from pathlib import Path

from fortress_services.quadlet import render_quadlet_service


REPO_ROOT = Path(__file__).resolve().parents[1]


class NewServiceRunbookTests(unittest.TestCase):
    def test_runbook_documents_new_service_authoring_and_deployment(self):
        runbook = REPO_ROOT / "runbooks" / "new-service.md"

        self.assertTrue(runbook.is_file())
        content = runbook.read_text()
        expected_phrases = [
            "inventory/services/<service>.yaml",
            "Service yaml does not declare NAS Endpoint, Dataset, Share, or protocol details directly",
            "Backend",
            "hostname",
            "Ingress defaults",
            "Published Ports",
            "Service Group",
            "Container Alias",
            "Service-owned volume",
            "Share-backed Volume",
            "Service Secret",
            "created",
            "version",
            "value",
            "secrets.<purpose>.value",
            "env_value: secret_name",
            "env_value: file_path",
            "Quadlet Fragment",
            "Service Data Owner",
            "existing Backend VM Mount",
            "service-deploy may validate Share-backed Volume subpaths",
            "does not run NAS Reconcile",
            "does not create NAS Shares",
            "does not create VM Mount units",
            "VM placement is the Service security boundary",
            "rootful system units",
            "Service Data Directory cleanup/migration is explicit",
            "service-deploy never prunes /srv/services/<service>/",
            "Service deletion/destruction is not automated in issue 07",
        ]

        for phrase in expected_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, content)

    def test_acceptance_demo_service_shape_is_renderable(self):
        service = {
            "name": "fortress-service-demo",
            "hostname": "fortress-service-demo.fearn.cloud",
            "service_group": "service-demo",
            "service_data_owner": {"uid": 1000, "gid": 1000},
            "backend": {"vm": "wintermute-demo", "port": 8080},
            "ingress": {
                "enabled": True,
                "exposure": "lan_only",
                "tls": "letsencrypt_dns",
                "auth": {"type": "none"},
            },
            "deploy": {
                "type": "quadlet",
                "containers": [
                    {
                        "name": "web",
                        "image": "docker.io/library/nginx:1.27",
                        "depends_on": ["postgres", "redis"],
                        "published_ports": [
                            {"bind": "127.0.0.1", "host": 8080, "container": 80, "ingress": True},
                            {"bind": "127.0.0.1", "host": 18080, "container": 80},
                        ],
                        "volumes": [
                            {
                                "service_path": "web",
                                "container": "/srv/fortress-demo-owned",
                                "access": "read_write",
                            },
                            {
                                "mount": "nfs-demo",
                                "source": "/",
                                "container": "/mnt/shared",
                                "access": "read_write",
                            },
                        ],
                        "secrets": [{"secret": "secrets.demo_password", "env": "DEMO_PASSWORD_FILE"}],
                    },
                    {
                        "name": "postgres",
                        "image": "docker.io/library/postgres:16",
                        "secrets": [{"secret": "secrets.demo_password", "env": "POSTGRES_PASSWORD_FILE"}],
                        "volumes": [
                            {
                                "service_path": "postgres",
                                "container": "/var/lib/postgresql/data",
                                "access": "read_write",
                            },
                        ],
                    },
                    {"name": "redis", "image": "docker.io/library/redis:7"},
                ],
            },
        }
        vm = {
            "mounts": [
                {
                    "name": "nfs-demo",
                    "dataset": "acceptance-nfs-demo",
                    "protocol": "nfs",
                    "mount_point": "/mnt/nfs-demo",
                    "access": "read_write",
                }
            ]
        }

        rendered = render_quadlet_service(service, vm, inventory_root=REPO_ROOT / "inventory" / "acceptance")

        containers = service["deploy"]["containers"]
        self.assertEqual(["web", "postgres", "redis"], [container["name"] for container in containers])
        self.assertEqual(["postgres", "redis"], containers[0]["depends_on"])
        self.assertEqual(
            [
                {"bind": "127.0.0.1", "host": 8080, "container": 80, "ingress": True},
                {"bind": "127.0.0.1", "host": 18080, "container": 80},
            ],
            containers[0]["published_ports"],
        )
        self.assertIn(
            {"service_path": "web", "container": "/srv/fortress-demo-owned", "access": "read_write"},
            containers[0]["volumes"],
        )
        self.assertIn(
            {"mount": "nfs-demo", "source": "/", "container": "/mnt/shared", "access": "read_write"},
            containers[0]["volumes"],
        )
        self.assertEqual(
            [{"secret": "secrets.demo_password", "env": "DEMO_PASSWORD_FILE"}],
            containers[0]["secrets"],
        )
        self.assertIn("fortress-group-service-demo.network", rendered.artifacts_by_filename)
        web = rendered.artifacts_by_filename["fortress-fortress-service-demo-web.container"]
        self.assertIn("NetworkAlias=web\n", web.content)
        self.assertIn("Network=fortress-group-service-demo\n", web.content)
        self.assertIn("Requires=fortress-fortress-service-demo-postgres.service fortress-fortress-service-demo-redis.service mnt-nfs\\x2ddemo.mount\n", web.content)
        self.assertIn("PublishPort=127.0.0.1:8080:80/tcp\n", web.content)
        self.assertIn("PublishPort=127.0.0.1:18080:80/tcp\n", web.content)
        self.assertIn("Secret=fortress_fortress-service-demo_demo_password\n", web.content)
        self.assertIn("Volume=/srv/services/fortress-service-demo/web:/srv/fortress-demo-owned:rw\n", web.content)
        self.assertIn("Volume=/mnt/nfs-demo:/mnt/shared:rw\n", web.content)
        self.assertIn("Notify=false\n", web.content)
        self.assertIn("RestartSec=5\n", web.content)

    def test_acceptance_demo_service_secret_example_uses_structured_shape(self):
        example = REPO_ROOT / "inventory" / "acceptance" / "service-demo.sops.yaml.example"

        self.assertTrue(example.is_file())
        content = example.read_text()
        self.assertIn("secrets:\n", content)
        self.assertIn("demo_password:\n", content)
        self.assertIn("created: 2026-05-12T00:00:00Z\n", content)
        self.assertIn("version: 1\n", content)
        self.assertIn("value:", content)


if __name__ == "__main__":
    unittest.main()
