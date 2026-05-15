import tempfile
import unittest
from pathlib import Path

from fortress_inventory.model import load_inventory_tree


class AcceptanceLifecycleTests(unittest.TestCase):
    def test_nfs_lifecycle_resolves_intent_and_writes_common_generated_artifacts(self):
        from fortress_acceptance.lifecycle import AcceptanceTestLifecycle

        with tempfile.TemporaryDirectory() as tmp:
            root = self._fixture(tmp)
            lifecycle = AcceptanceTestLifecycle(
                policy_name="nfs-shared-mount",
                artifact_label="NFS shared-mount Acceptance",
                purpose="nfs-shared-mount-acceptance",
            )
            intent = lifecycle.resolve_intent(
                root,
                load_inventory_tree(root),
                {"host": "wintermute", "template": "debian-13-base", "endpoint": "truenas"},
            )

            self.assertEqual("acceptance-nfs-demo", intent["dataset"]["name"])
            self.assertEqual(["tmp-nfs-primary", "tmp-nfs-peer"], [vm["name"] for vm in intent["vms"]])
            lifecycle.write_generated_dataset(root, intent)
            lifecycle.write_generated_vms(root, intent)

            dataset_yaml = (root / "inventory" / "datasets" / "acceptance-nfs-demo.yaml").read_text()
            primary_yaml = (root / "inventory" / "vms" / "tmp-nfs-primary.yaml").read_text()
            self.assertIn("name: acceptance-nfs-demo", dataset_yaml)
            self.assertIn("lifecycle: ephemeral", dataset_yaml)
            self.assertIn("purpose: nfs-shared-mount-acceptance", primary_yaml)
            self.assertIn("dataset: acceptance-nfs-demo", primary_yaml)
            self.assertIn("mount_point: /mnt/nfs-demo", primary_yaml)

    def test_service_layer_lifecycle_resolves_endpoint_config_and_common_artifacts(self):
        from fortress_acceptance.lifecycle import AcceptanceTestLifecycle

        with tempfile.TemporaryDirectory() as tmp:
            root = self._fixture(tmp)
            (root / "inventory" / "acceptance" / "service-layer.yaml").write_text(
                "dataset: acceptance-service-layer\n"
                "mount:\n"
                "  name: service-layer\n"
                "  mount_point: /mnt/service-layer\n"
                "  access: read_write\n"
                "hardware:\n"
                "  cores: 1\n"
                "  memory: 1024\n"
                "  disk_size: 8G\n"
                "storage_by_host:\n"
                "  wintermute: fast\n"
                "vms:\n"
                "  primary:\n"
                "    name: tmp-service-primary\n"
                "    vmid: 8921\n"
                "    address_by_host:\n"
                "      wintermute: 10.10.0.233/24\n"
                "  peer:\n"
                "    name: tmp-service-peer\n"
                "    vmid: 8922\n"
                "    address_by_host:\n"
                "      wintermute: 10.10.0.234/24\n"
            )
            lifecycle = AcceptanceTestLifecycle(
                policy_name="service-layer",
                artifact_label="Service-layer Acceptance",
                purpose="service-layer-acceptance",
            )
            intent = lifecycle.resolve_intent(
                root,
                load_inventory_tree(root),
                {"host": "wintermute", "template": "debian-13-base", "endpoint": "truenas"},
            )

            self.assertEqual("10.10.0.15", intent["endpoint_config"]["management_address"])
            self.assertEqual("acceptance-service-layer", intent["dataset"]["name"])
            self.assertEqual(["tmp-service-primary", "tmp-service-peer"], [vm["name"] for vm in intent["vms"]])

            lifecycle.write_generated_dataset(root, intent)
            lifecycle.write_generated_vms(root, intent)

            dataset_yaml = (root / "inventory" / "datasets" / "acceptance-service-layer.yaml").read_text()
            primary_yaml = (root / "inventory" / "vms" / "tmp-service-primary.yaml").read_text()
            self.assertIn("name: acceptance-service-layer", dataset_yaml)
            self.assertIn("purpose: service-layer-acceptance", primary_yaml)
            self.assertIn("dataset: acceptance-service-layer", primary_yaml)

    def _fixture(self, tmp):
        root = Path(tmp)
        inventory = root / "inventory"
        for subdir in ["acceptance", "hosts", "templates", "vms", "datasets", "nas"]:
            (inventory / subdir).mkdir(parents=True, exist_ok=True)
        (inventory / "acceptance" / "nfs-shared-mount.yaml").write_text(
            "dataset: acceptance-nfs-demo\n"
            "mount:\n"
            "  name: nfs-demo\n"
            "  mount_point: /mnt/nfs-demo\n"
            "  access: read_write\n"
            "hardware:\n"
            "  cores: 1\n"
            "  memory: 1024\n"
            "  disk_size: 8G\n"
            "storage_by_host:\n"
            "  wintermute: fast\n"
            "vms:\n"
            "  primary:\n"
            "    name: tmp-nfs-primary\n"
            "    vmid: 8911\n"
            "    address_by_host:\n"
            "      wintermute: 10.10.0.231/24\n"
            "  peer:\n"
            "    name: tmp-nfs-peer\n"
            "    vmid: 8912\n"
            "    address_by_host:\n"
            "      wintermute: 10.10.0.232/24\n"
        )
        (inventory / "hosts" / "wintermute.yaml").write_text(
            "proxmox:\n"
            "  templates: [debian-13-base]\n"
            "network:\n"
            "  bridges:\n"
            "    - name: vmbr0\n"
            "      cidr: 10.10.0.11/24\n"
            "      gateway: 10.10.0.1\n"
        )
        (inventory / "templates" / "debian-13-base.yaml").write_text("name: debian-13-base\nvmid: 9001\n")
        (inventory / "nas" / "truenas.yaml").write_text("name: truenas\nmanagement_address: 10.10.0.15\n")
        return root


if __name__ == "__main__":
    unittest.main()
