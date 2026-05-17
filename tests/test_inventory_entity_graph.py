import unittest
from pathlib import Path

from fortress_inventory.entity_graph import (
    AcceptanceEphemeralDatasetFact,
    AcceptanceOperationalVmFact,
    AcceptancePolicyIntent,
    DesiredNfsShareInput,
    HostUpdateImpactedVm,
    HostUpdateRebootImpact,
    MountDatasetFact,
    HostBridgeFact,
    InventoryEntityGraph,
    InventoryEntityGraphError,
    ServiceGroupLaunchIntent,
    ServiceLaunchIntent,
    ServiceShareBackedVolumeFact,
    TemplateLineageVmFact,
    TemplateVerificationIntent,
    VmLifecycleSelectedHostFacts,
    VmMountFact,
    VmUpdateRebootImpact,
)
from fortress_inventory.model import InventoryModel, load_inventory_tree


REPO_ROOT = Path(__file__).resolve().parents[1]


def inventory_model(hosts=None, vms=None, services=None, datasets=None, nas_endpoints=None):
    return InventoryModel(
        root=None,
        hosts=hosts or {},
        vms=vms or {},
        services=services or {},
        datasets=datasets or {},
        nas_endpoints=nas_endpoints or {},
        templates={},
        template_verification_policy={},
        acceptance_policies={},
        globals={},
    )


class InventoryEntityGraphTests(unittest.TestCase):
    def test_resolves_vm_mount_by_vm_name_and_mount_name(self):
        model = inventory_model(
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
                    ],
                },
            },
        )

        graph = InventoryEntityGraph(model)

        self.assertEqual(
            VmMountFact(
                vm_name="media01",
                name="media",
                dataset_name="media",
                protocol="nfs",
                mount_point="/mnt/nas/media",
                access="read_write",
            ),
            graph.vm_mount("media01", "media"),
        )
        self.assertIsNone(graph.vm_mount("media01", "archive"))
        self.assertIsNone(graph.vm_mount("missing-vm", "media"))

    def test_vm_mount_lookup_rejects_duplicate_mount_names_on_vm(self):
        model = inventory_model(
            vms={
                "media01": {
                    "mounts": [
                        {"name": "media", "dataset": "media"},
                        {"name": "media", "dataset": "archive"},
                    ],
                },
            },
        )

        graph = InventoryEntityGraph(model)

        with self.assertRaisesRegex(
            InventoryEntityGraphError,
            "VM media01 declares duplicate Mount Name media",
        ):
            graph.vm_mount("media01", "media")

    def test_resolves_vm_mount_to_dataset_facts(self):
        model = inventory_model(
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
                    ],
                },
            },
            datasets={
                "media": {
                    "name": "media",
                    "nas": "truenas",
                    "path": "/mnt/pool/media",
                    "lifecycle": "adopted",
                    "owner": {"uid": 1000, "gid": 1000},
                },
            },
        )

        graph = InventoryEntityGraph(model)

        self.assertEqual(
            MountDatasetFact(
                vm_name="media01",
                mount_name="media",
                dataset_name="media",
                nas_endpoint_name="truenas",
                path="/mnt/pool/media",
                lifecycle="adopted",
                owner={"uid": 1000, "gid": 1000},
            ),
            graph.vm_mount_dataset_facts("media01", "media"),
        )
        self.assertIsNone(graph.vm_mount_dataset_facts("media01", "archive"))

    def test_mount_dataset_resolution_rejects_duplicate_dataset_names(self):
        model = inventory_model(
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
                    ],
                },
            },
            datasets={
                "media-a": {"name": "media", "path": "/mnt/pool/media-a"},
                "media-b": {"name": "media", "path": "/mnt/pool/media-b"},
            },
        )

        graph = InventoryEntityGraph(model)

        with self.assertRaisesRegex(
            InventoryEntityGraphError,
            "Dataset name media is declared by multiple Dataset Entities",
        ):
            graph.vm_mount_dataset_facts("media01", "media")

    def test_mount_dataset_resolution_rejects_missing_dataset_reference(self):
        model = inventory_model(
            vms={
                "media01": {
                    "mounts": [
                        {"name": "media", "dataset": "missing-media"},
                    ],
                },
            },
        )

        graph = InventoryEntityGraph(model)

        with self.assertRaisesRegex(
            InventoryEntityGraphError,
            "VM media01 Mount media references missing Dataset missing-media",
        ):
            graph.vm_mount_dataset_facts("media01", "media")

    def test_resolves_vm_nfs_client_addresses_from_static_ipv4_facts(self):
        model = inventory_model(
            vms={
                "media01": {
                    "network": {
                        "interfaces": [
                            {"address": "10.0.10.101/24"},
                            {"address": "2001:db8::10/64"},
                        ],
                    },
                },
                "dynamic01": {"network": {"interfaces": [{"bridge": "vmbr0"}]}},
            },
        )

        graph = InventoryEntityGraph(model)

        self.assertEqual(("10.0.10.101",), graph.vm_nfs_client_addresses("media01"))
        self.assertEqual((), graph.vm_nfs_client_addresses("dynamic01"))
        self.assertEqual((), graph.vm_nfs_client_addresses("missing-vm"))

    def test_vm_nfs_client_addresses_reject_invalid_declared_address_facts(self):
        model = inventory_model(
            vms={
                "media01": {
                    "network": {
                        "interfaces": [
                            {"address": "not-an-address"},
                        ],
                    },
                },
            },
        )

        graph = InventoryEntityGraph(model)

        with self.assertRaisesRegex(
            InventoryEntityGraphError,
            "VM media01 declares invalid network.interfaces\\[0\\].address",
        ):
            graph.vm_nfs_client_addresses("media01")

    def test_exposes_derived_nfs_share_planning_inputs(self):
        model = inventory_model(
            vms={
                "media01": {
                    "network": {"interfaces": [{"address": "10.0.10.101/24"}]},
                    "mounts": [
                        {
                            "name": "media",
                            "dataset": "media",
                            "protocol": "nfs",
                            "mount_point": "/mnt/nas/media",
                            "access": "read_write",
                        },
                    ],
                },
                "worker01": {
                    "network": {"interfaces": [{"address": "10.0.10.102/24"}]},
                    "mounts": [
                        {
                            "name": "media",
                            "dataset": "media",
                            "protocol": "nfs",
                            "mount_point": "/mnt/nas/media",
                            "access": "read_write",
                        },
                    ],
                },
                "scratch01": {
                    "network": {"interfaces": [{"address": "10.0.10.103/24"}]},
                    "mounts": [
                        {
                            "name": "scratch",
                            "dataset": "scratch",
                            "protocol": "nfs",
                            "mount_point": "/mnt/nas/scratch",
                            "access": "read_write",
                        },
                    ],
                },
            },
            datasets={
                "media": {
                    "name": "media",
                    "path": "/mnt/pool/media",
                    "lifecycle": "adopted",
                },
                "scratch": {
                    "name": "scratch",
                    "path": "/mnt/pool/scratch",
                    "lifecycle": "ephemeral",
                },
            },
        )

        graph = InventoryEntityGraph(model)

        self.assertEqual(
            (
                DesiredNfsShareInput(
                    dataset_name="media",
                    path="/mnt/pool/media",
                    protocol="nfs",
                    access="read_write",
                    lifecycle="adopted",
                    client_addresses=("10.0.10.101", "10.0.10.102"),
                ),
            ),
            graph.desired_nfs_share_inputs(),
        )
        self.assertEqual(
            (
                DesiredNfsShareInput(
                    dataset_name="media",
                    path="/mnt/pool/media",
                    protocol="nfs",
                    access="read_write",
                    lifecycle="adopted",
                    client_addresses=("10.0.10.101", "10.0.10.102"),
                ),
                DesiredNfsShareInput(
                    dataset_name="scratch",
                    path="/mnt/pool/scratch",
                    protocol="nfs",
                    access="read_write",
                    lifecycle="ephemeral",
                    client_addresses=("10.0.10.103",),
                ),
            ),
            graph.desired_nfs_share_inputs(include_ephemeral_datasets=True),
        )

    def test_resolves_service_share_backed_volumes_through_backend_vm_mounts(self):
        model = inventory_model(
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
                    ],
                },
            },
            services={
                "photos": {
                    "backend": {"vm": "media01", "port": 2283},
                    "deploy": {
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
                                ],
                            },
                        ],
                    },
                },
            },
        )

        graph = InventoryEntityGraph(model)

        self.assertEqual(
            (
                ServiceShareBackedVolumeFact(
                    service_name="photos",
                    vm_name="media01",
                    container_name="server",
                    mount_name="media",
                    dataset_name="media",
                    source="photos",
                    container_path="/photos",
                    access="read_only",
                    mount_point="/mnt/nas/media",
                    source_path="/mnt/nas/media/photos",
                ),
            ),
            graph.service_share_backed_volumes("photos"),
        )
        self.assertEqual((), graph.service_share_backed_volumes("missing-service"))

    def test_service_share_backed_volume_resolution_rejects_missing_references(self):
        model = inventory_model(
            vms={"media01": {"mounts": []}},
            services={
                "photos": {
                    "backend": {"vm": "media01", "port": 2283},
                    "deploy": {
                        "containers": [
                            {
                                "name": "server",
                                "volumes": [
                                    {"mount": "media", "source": "/", "container": "/photos"},
                                ],
                            },
                        ],
                    },
                },
                "notes": {
                    "backend": {"vm": "missing-vm", "port": 8080},
                    "deploy": {
                        "containers": [
                            {
                                "name": "server",
                                "volumes": [
                                    {"mount": "data", "source": "/", "container": "/data"},
                                ],
                            },
                        ],
                    },
                },
            },
        )

        graph = InventoryEntityGraph(model)

        with self.assertRaisesRegex(
            InventoryEntityGraphError,
            "Service photos Share-backed Volume references missing Mount Name media on Backend VM media01",
        ):
            graph.service_share_backed_volumes("photos")
        with self.assertRaisesRegex(
            InventoryEntityGraphError,
            "Service notes references missing Backend VM missing-vm",
        ):
            graph.service_share_backed_volumes("notes")

    def test_resolves_service_backend_vm_name_from_service_name(self):
        model = inventory_model(
            services={
                "photos": {
                    "backend": {"vm": "media01", "port": 2283},
                },
            },
        )

        graph = InventoryEntityGraph(model)

        self.assertEqual("media01", graph.service_backend_vm_name("photos"))
        self.assertEqual(2283, graph.service_backend_port("photos"))
        self.assertIsNone(graph.service_backend_vm_name("missing-service"))
        self.assertIsNone(graph.service_backend_port("missing-service"))

    def test_service_backend_vm_name_rejects_non_singular_backend_declaration(self):
        model = inventory_model(
            services={
                "photos": {
                    "backend": [{"vm": "media01", "port": 2283}],
                },
            },
        )

        graph = InventoryEntityGraph(model)

        with self.assertRaisesRegex(InventoryEntityGraphError, "Service photos must declare one singular Backend"):
            graph.service_backend_vm_name("photos")

    def test_resolves_service_launch_intent_from_service_name(self):
        model = inventory_model(
            vms={"media01": {}},
            services={
                "photos": {
                    "backend": {"vm": "media01", "port": 2283},
                    "ingress": {"enabled": True},
                },
            },
        )

        graph = InventoryEntityGraph(model)

        self.assertEqual(
            ServiceLaunchIntent(
                service_name="photos",
                backend_vm_name="media01",
                requires_ingress_regeneration=True,
            ),
            graph.service_launch_intent("photos"),
        )
        self.assertIsNone(graph.service_launch_intent("missing-service"))

    def test_service_launch_intent_rejects_missing_backend_vm_reference(self):
        model = inventory_model(
            services={
                "photos": {
                    "backend": {"vm": "missing-vm", "port": 2283},
                    "ingress": {"enabled": False},
                },
            },
        )

        graph = InventoryEntityGraph(model)

        with self.assertRaisesRegex(
            InventoryEntityGraphError,
            "Service photos references missing Backend VM missing-vm",
        ):
            graph.service_launch_intent("photos")

    def test_resolves_media_service_group_launch_intent_from_inventory(self):
        graph = InventoryEntityGraph(load_inventory_tree(REPO_ROOT))

        self.assertEqual(
            ServiceGroupLaunchIntent(
                service_group_name="media",
                backend_vm_name="media-vm",
                service_names=("prowlarr", "sonarr", "radarr", "bazarr", "jellyfin", "seerr"),
                requires_ingress_regeneration=True,
            ),
            graph.service_group_launch_intent("media"),
        )

    def test_service_group_launch_intent_rejects_unknown_service_group(self):
        graph = InventoryEntityGraph(inventory_model())

        with self.assertRaisesRegex(
            InventoryEntityGraphError,
            "Service Group missing is not declared",
        ):
            graph.service_group_launch_intent("missing")

    def test_service_group_launch_intent_rejects_group_without_launch_metadata(self):
        model = inventory_model(
            services={
                "photos": {
                    "service_group": "media",
                    "backend": {"vm": "media-vm"},
                },
            },
            vms={"media-vm": {}},
        )
        graph = InventoryEntityGraph(model)

        with self.assertRaisesRegex(
            InventoryEntityGraphError,
            "Service Group media is not launchable; no Backend VM declares launch metadata",
        ):
            graph.service_group_launch_intent("media")

    def test_service_group_launch_intent_rejects_missing_backend_vm(self):
        model = inventory_model(
            services={
                "photos": {
                    "service_group": "media",
                    "backend": {"vm": "missing-vm"},
                },
            },
            vms={
                "media-vm": {
                    "launchable_service_groups": [
                        {"name": "media", "launch_order": ["photos"]},
                    ],
                },
            },
        )
        graph = InventoryEntityGraph(model)

        with self.assertRaisesRegex(
            InventoryEntityGraphError,
            "Service Group Launch media Service photos references missing Backend VM missing-vm",
        ):
            graph.service_group_launch_intent("media")

    def test_service_group_launch_intent_rejects_mixed_backend_vms(self):
        model = inventory_model(
            services={
                "photos": {
                    "service_group": "media",
                    "backend": {"vm": "media-vm"},
                },
                "downloads": {
                    "service_group": "media",
                    "backend": {"vm": "download-vm"},
                },
            },
            vms={
                "media-vm": {
                    "launchable_service_groups": [
                        {"name": "media", "launch_order": ["photos", "downloads"]},
                    ],
                },
                "download-vm": {},
            },
        )
        graph = InventoryEntityGraph(model)

        with self.assertRaisesRegex(
            InventoryEntityGraphError,
            "Service Group Launch media requires shared Backend VM media-vm; Service downloads uses download-vm",
        ):
            graph.service_group_launch_intent("media")

    def test_service_group_launch_intent_rejects_mixed_backend_group_members(self):
        model = inventory_model(
            services={
                "photos": {
                    "service_group": "media",
                    "backend": {"vm": "media-vm"},
                },
                "downloads": {
                    "service_group": "media",
                    "backend": {"vm": "download-vm"},
                },
            },
            vms={
                "media-vm": {
                    "launchable_service_groups": [
                        {"name": "media", "launch_order": ["photos"]},
                    ],
                },
                "download-vm": {},
            },
        )
        graph = InventoryEntityGraph(model)

        with self.assertRaisesRegex(
            InventoryEntityGraphError,
            "Service Group Launch media requires shared Backend VM media-vm; Service downloads uses download-vm",
        ):
            graph.service_group_launch_intent("media")

    def test_service_group_launch_intent_rejects_omitted_group_member(self):
        model = inventory_model(
            services={
                "photos": {
                    "service_group": "media",
                    "backend": {"vm": "media-vm"},
                },
                "catalog": {
                    "service_group": "media",
                    "backend": {"vm": "media-vm"},
                },
            },
            vms={
                "media-vm": {
                    "launchable_service_groups": [
                        {"name": "media", "launch_order": ["photos"]},
                    ],
                },
            },
        )
        graph = InventoryEntityGraph(model)

        with self.assertRaisesRegex(
            InventoryEntityGraphError,
            "Service Group Launch media omits Service catalog from Launch Order",
        ):
            graph.service_group_launch_intent("media")

    def test_resolves_vm_placement_host_name_from_vm_name(self):
        model = inventory_model(
            vms={
                "media01": {
                    "placement": {"host": "wintermute"},
                },
            },
        )

        graph = InventoryEntityGraph(model)

        self.assertEqual("wintermute", graph.vm_placement_host_name("media01"))

    def test_resolves_vm_lifecycle_selected_host_provider_facts(self):
        model = inventory_model(
            hosts={"wintermute": {}, "straylight": {}},
            vms={
                "media01": {
                    "placement": {"host": "wintermute"},
                },
            },
        )

        graph = InventoryEntityGraph(model)

        self.assertEqual(
            VmLifecycleSelectedHostFacts(
                vm_name="media01",
                placement_host_name="wintermute",
                provider_host_names=("straylight", "wintermute"),
            ),
            graph.vm_lifecycle_selected_host_facts("media01", provider_host_names=("straylight",)),
        )
        self.assertIsNone(graph.vm_lifecycle_selected_host_facts("missing-vm"))

    def test_resolves_host_update_reboot_impact_from_placed_vms_and_resident_services(self):
        model = inventory_model(
            hosts={"wintermute": {}, "straylight": {}},
            vms={
                "media01": {"vmid": 101, "placement": {"host": "wintermute"}},
                "forgejo01": {"vmid": 102, "placement": {"host": "wintermute"}},
                "dns01": {"vmid": 201, "placement": {"host": "straylight"}},
            },
            services={
                "jellyfin": {"backend": {"vm": "media01"}},
                "forgejo": {"backend": {"vm": "forgejo01"}},
                "unbound": {"backend": {"vm": "dns01"}},
            },
        )

        graph = InventoryEntityGraph(model)

        self.assertEqual(
            HostUpdateRebootImpact(
                host_name="wintermute",
                ordinary_vms=(
                    HostUpdateImpactedVm(vm_name="forgejo01", vmid=102),
                    HostUpdateImpactedVm(vm_name="media01", vmid=101),
                ),
                resident_service_names=("forgejo", "jellyfin"),
            ),
            graph.host_update_reboot_impact("wintermute"),
        )
        self.assertIsNone(graph.host_update_reboot_impact("missing-host"))

    def test_resolves_vm_update_reboot_impact_from_resident_services(self):
        model = inventory_model(
            vms={
                "media01": {"vmid": 101},
                "forgejo01": {"vmid": 102},
            },
            services={
                "jellyfin": {"backend": {"vm": "media01"}},
                "sonarr": {"backend": {"vm": "media01"}},
                "forgejo": {"backend": {"vm": "forgejo01"}},
            },
        )

        graph = InventoryEntityGraph(model)

        self.assertEqual(
            VmUpdateRebootImpact(
                vm_name="media01",
                resident_service_names=("jellyfin", "sonarr"),
            ),
            graph.vm_update_reboot_impact("media01"),
        )
        self.assertIsNone(graph.vm_update_reboot_impact("missing-vm"))

    def test_vm_lifecycle_selected_host_provider_facts_reject_invalid_declared_hosts(self):
        model = inventory_model(
            hosts={"wintermute": {}},
            vms={
                "media01": {"placement": {"host": "missing-host"}},
                "headless": {},
            },
        )

        graph = InventoryEntityGraph(model)

        with self.assertRaisesRegex(InventoryEntityGraphError, "VM headless has no placement.host"):
            graph.vm_lifecycle_selected_host_facts("headless")
        with self.assertRaisesRegex(
            InventoryEntityGraphError,
            "VM media01 selected Host provider coverage references missing Host\\(s\\): missing-host, straylight",
        ):
            graph.vm_lifecycle_selected_host_facts("media01", provider_host_names=("straylight",))

    def test_returns_normalized_vm_static_ipv4_addresses_from_vm_name(self):
        model = inventory_model(
            vms={
                "media01": {
                    "network": {
                        "interfaces": [
                            {"bridge": "vmbr0", "address": "10.0.10.101/24"},
                            {"bridge": "vmbr1", "address": "2001:db8::10/64"},
                        ],
                    },
                },
            },
        )

        graph = InventoryEntityGraph(model)

        self.assertEqual(("10.0.10.101",), graph.vm_static_ipv4_addresses("media01"))

    def test_singular_vm_static_ipv4_address_returns_none_for_absence_and_rejects_ambiguity(self):
        model = inventory_model(
            vms={
                "dynamic01": {"network": {"interfaces": [{"bridge": "vmbr0"}]}},
                "multi01": {
                    "network": {
                        "interfaces": [
                            {"bridge": "vmbr0", "address": "10.0.10.101/24"},
                            {"bridge": "vmbr1", "address": "10.0.20.101/24"},
                        ],
                    },
                },
            },
        )

        graph = InventoryEntityGraph(model)

        self.assertIsNone(graph.vm_static_ipv4_address("dynamic01"))
        with self.assertRaisesRegex(
            InventoryEntityGraphError,
            "VM multi01 must declare at most one static IPv4 address",
        ):
            graph.vm_static_ipv4_address("multi01")

    def test_vm_static_ipv4_addresses_reject_malformed_declared_address(self):
        model = inventory_model(
            vms={
                "media01": {
                    "network": {
                        "interfaces": [
                            {"bridge": "vmbr0", "address": "not-an-address"},
                        ],
                    },
                },
            },
        )

        graph = InventoryEntityGraph(model)

        with self.assertRaisesRegex(
            InventoryEntityGraphError,
            "VM media01 declares invalid network.interfaces\\[0\\].address",
        ):
            graph.vm_static_ipv4_addresses("media01")

    def test_returns_normalized_host_management_ipv4_address_from_host_name(self):
        model = inventory_model(
            hosts={
                "wintermute": {
                    "network": {
                        "management_address": "10.0.0.10/24",
                    },
                },
                "straylight": {
                    "network": {},
                },
            },
        )

        graph = InventoryEntityGraph(model)

        self.assertEqual("10.0.0.10", graph.host_management_ipv4_address("wintermute"))
        self.assertIsNone(graph.host_management_ipv4_address("straylight"))

    def test_host_management_ipv4_address_rejects_malformed_or_non_ipv4_declared_address(self):
        cases = {
            "bad": "not-an-address",
            "v6": "2001:db8::10/64",
        }

        for host_name, address in cases.items():
            with self.subTest(host_name=host_name):
                graph = InventoryEntityGraph(
                    inventory_model(hosts={host_name: {"network": {"management_address": address}}})
                )

                with self.assertRaisesRegex(
                    InventoryEntityGraphError,
                    f"Host {host_name} must declare network.management_address as an IPv4 address",
                ):
                    graph.host_management_ipv4_address(host_name)

    def test_returns_host_bridge_name_matching_ipv4_address(self):
        model = inventory_model(
            hosts={
                "wintermute": {
                    "network": {
                        "bridges": [
                            {"name": "vmbr0", "managed": False, "cidr": "10.0.10.1/24"},
                            {"name": "vmbr1", "managed": False, "cidr": "10.0.20.1/24"},
                        ],
                    },
                },
            },
        )

        graph = InventoryEntityGraph(model)

        self.assertEqual(
            "vmbr0",
            graph.host_bridge_name_matching_address("wintermute", "10.0.10.101/24"),
        )
        self.assertIsNone(graph.host_bridge_name_matching_address("wintermute", "10.0.30.101/24"))

    def test_host_bridge_matching_address_rejects_ambiguous_bridge_cidrs(self):
        model = inventory_model(
            hosts={
                "wintermute": {
                    "network": {
                        "bridges": [
                            {"name": "vmbr0", "managed": False, "cidr": "10.0.10.1/24"},
                            {"name": "vmbr1", "managed": False, "cidr": "10.0.10.1/25"},
                        ],
                    },
                },
            },
        )

        graph = InventoryEntityGraph(model)

        with self.assertRaisesRegex(
            InventoryEntityGraphError,
            "Host wintermute address 10.0.10.101/24 matches multiple bridge CIDRs: vmbr0, vmbr1",
        ):
            graph.host_bridge_name_matching_address("wintermute", "10.0.10.101/24")

    def test_host_bridge_matching_address_rejects_malformed_declared_bridge_cidr(self):
        model = inventory_model(
            hosts={
                "wintermute": {
                    "network": {
                        "bridges": [
                            {"name": "vmbr0", "managed": False, "cidr": "not-a-cidr"},
                        ],
                    },
                },
            },
        )

        graph = InventoryEntityGraph(model)

        with self.assertRaisesRegex(
            InventoryEntityGraphError,
            "Host wintermute bridge vmbr0 declares invalid cidr",
        ):
            graph.host_bridge_name_matching_address("wintermute", "10.0.10.101/24")

    def test_host_bridge_matching_address_rejects_malformed_address(self):
        model = inventory_model(
            hosts={
                "wintermute": {
                    "network": {
                        "bridges": [
                            {"name": "vmbr0", "managed": False, "cidr": "10.0.10.1/24"},
                        ],
                    },
                },
            },
        )

        graph = InventoryEntityGraph(model)

        with self.assertRaisesRegex(
            InventoryEntityGraphError,
            "Host wintermute bridge lookup address must be an IPv4 address",
        ):
            graph.host_bridge_name_matching_address("wintermute", "not-an-address")

    def test_resolves_template_verification_intent_for_selected_host_and_template(self):
        model = InventoryModel(
            root=None,
            hosts={
                "wintermute": {
                    "proxmox": {"templates": ["debian-13-base"]},
                    "network": {
                        "management_address": "10.10.0.11/24",
                        "bridges": [
                            {"name": "vmbr0", "cidr": "10.10.0.1/24", "gateway": "10.10.0.1"},
                        ],
                    },
                },
            },
            vms={},
            services={},
            datasets={},
            nas_endpoints={},
            templates={"debian-13-base": {"name": "debian-13-base", "vmid": 9001}},
            template_verification_policy={
                "vmid": 8901,
                "hardware": {"cores": 1, "memory": 1024, "disk_size": "8G"},
                "storage_by_host": {"wintermute": "fast"},
                "address_by_host": {"wintermute": "10.10.0.221/24"},
            },
            acceptance_policies={},
            globals={},
        )

        graph = InventoryEntityGraph(model)

        self.assertEqual(
            TemplateVerificationIntent(
                host_name="wintermute",
                template_name="debian-13-base",
                management_address="10.10.0.11",
                vmid=8901,
                hardware={"cores": 1, "memory": 1024, "disk_size": "8G"},
                storage="fast",
                static_address="10.10.0.221/24",
                bridge=HostBridgeFact(name="vmbr0", cidr="10.10.0.1/24", gateway="10.10.0.1"),
            ),
            graph.template_verification_intent("wintermute", "debian-13-base"),
        )
        self.assertIsNone(graph.template_verification_intent("missing-host", "debian-13-base"))

    def test_resolves_template_update_scope_and_existing_vm_lineage(self):
        model = InventoryModel(
            root=None,
            hosts={
                "wintermute": {"proxmox": {"templates": ["debian-13-base"]}},
                "molly": {"proxmox": {"templates": ["debian-13-base", "ubuntu-2404-base"]}},
                "straylight": {"proxmox": {"templates": ["ubuntu-2404-base"]}},
            },
            vms={
                "media01": {
                    "vmid": 101,
                    "placement": {"host": "wintermute"},
                    "source": {"template": "debian-13-base"},
                },
                "dns01": {
                    "vmid": 102,
                    "placement": {"host": "molly"},
                    "source": {"template": "debian-13-base"},
                },
                "web01": {
                    "vmid": 103,
                    "placement": {"host": "straylight"},
                    "source": {"template": "ubuntu-2404-base"},
                },
            },
            services={},
            datasets={},
            nas_endpoints={},
            templates={"debian-13-base": {"name": "debian-13-base"}},
            template_verification_policy={},
            acceptance_policies={},
            globals={},
        )

        graph = InventoryEntityGraph(model)

        self.assertEqual(("molly", "wintermute"), graph.host_names_declaring_template("debian-13-base"))
        self.assertEqual(
            (
                TemplateLineageVmFact(
                    vm_name="dns01",
                    vmid=102,
                    placement_host_name="molly",
                    template_name="debian-13-base",
                ),
                TemplateLineageVmFact(
                    vm_name="media01",
                    vmid=101,
                    placement_host_name="wintermute",
                    template_name="debian-13-base",
                ),
            ),
            graph.template_lineage_vms("debian-13-base"),
        )

    def test_resolves_acceptance_policy_intent_for_selected_host_template_and_nas_endpoint(self):
        model = InventoryModel(
            root=None,
            hosts={
                "wintermute": {
                    "proxmox": {"templates": ["debian-13-base"]},
                    "network": {
                        "bridges": [
                            {"name": "vmbr0", "cidr": "10.10.0.1/24", "gateway": "10.10.0.1"},
                        ],
                    },
                },
            },
            vms={},
            services={},
            datasets={},
            nas_endpoints={"truenas": {"name": "truenas", "management_address": "10.10.0.15"}},
            templates={"debian-13-base": {"name": "debian-13-base", "vmid": 9001}},
            template_verification_policy={},
            acceptance_policies={
                "nfs-shared-mount": {
                    "dataset": "acceptance-nfs-demo",
                    "mount": {
                        "name": "nfs-demo",
                        "mount_point": "/mnt/nfs-demo",
                        "access": "read_write",
                    },
                    "hardware": {"cores": 1, "memory": 1024, "disk_size": "8G"},
                    "storage_by_host": {"wintermute": "fast"},
                    "vms": {
                        "primary": {
                            "name": "tmp-nfs-primary",
                            "vmid": 8911,
                            "address_by_host": {"wintermute": "10.10.0.231/24"},
                        },
                        "peer": {
                            "name": "tmp-nfs-peer",
                            "vmid": 8912,
                            "address_by_host": {"wintermute": "10.10.0.232/24"},
                        },
                    },
                },
            },
            globals={},
        )

        graph = InventoryEntityGraph(model)

        self.assertEqual(
            AcceptancePolicyIntent(
                policy_name="nfs-shared-mount",
                host_name="wintermute",
                template_name="debian-13-base",
                nas_endpoint_name="truenas",
                nas_endpoint={"name": "truenas", "management_address": "10.10.0.15"},
                hardware={"cores": 1, "memory": 1024, "disk_size": "8G"},
                storage="fast",
                mount={"name": "nfs-demo", "mount_point": "/mnt/nfs-demo", "access": "read_write"},
                dataset=AcceptanceEphemeralDatasetFact(
                    name="acceptance-nfs-demo",
                    nas_endpoint_name="truenas",
                    path="/mnt/tank/fortress-acceptance/nfs-demo",
                    lifecycle="ephemeral",
                ),
                vms=(
                    AcceptanceOperationalVmFact(
                        role="primary",
                        name="tmp-nfs-primary",
                        vmid=8911,
                        static_address="10.10.0.231/24",
                        client_address="10.10.0.231",
                        bridge=HostBridgeFact(name="vmbr0", cidr="10.10.0.1/24", gateway="10.10.0.1"),
                    ),
                    AcceptanceOperationalVmFact(
                        role="peer",
                        name="tmp-nfs-peer",
                        vmid=8912,
                        static_address="10.10.0.232/24",
                        client_address="10.10.0.232",
                        bridge=HostBridgeFact(name="vmbr0", cidr="10.10.0.1/24", gateway="10.10.0.1"),
                    ),
                ),
            ),
            graph.acceptance_policy_intent(
                "nfs-shared-mount",
                host_name="wintermute",
                template_name="debian-13-base",
                nas_endpoint_name="truenas",
            ),
        )
        with self.assertRaisesRegex(
            InventoryEntityGraphError,
            "Acceptance Policy 'missing-policy' is not declared",
        ):
            graph.acceptance_policy_intent(
                "missing-policy",
                host_name="wintermute",
                template_name="debian-13-base",
                nas_endpoint_name="truenas",
            )

    def test_acceptance_policy_intent_rejects_missing_selected_entities(self):
        model = InventoryModel(
            root=None,
            hosts={"wintermute": {}},
            vms={},
            services={},
            datasets={},
            nas_endpoints={"truenas": {"name": "truenas"}},
            templates={"debian-13-base": {"name": "debian-13-base"}},
            template_verification_policy={},
            acceptance_policies={"service-layer": {"dataset": "acceptance-service-layer"}},
            globals={},
        )
        graph = InventoryEntityGraph(model)

        cases = [
            (
                {"host_name": "missing-host", "template_name": "debian-13-base", "nas_endpoint_name": "truenas"},
                "Host 'missing-host' is not declared",
            ),
            (
                {"host_name": "wintermute", "template_name": "missing-template", "nas_endpoint_name": "truenas"},
                "Template 'missing-template' is not declared",
            ),
            (
                {"host_name": "wintermute", "template_name": "debian-13-base", "nas_endpoint_name": "missing-nas"},
                "NAS Endpoint 'missing-nas' is not declared",
            ),
        ]
        for kwargs, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(InventoryEntityGraphError, message):
                    graph.acceptance_policy_intent("service-layer", **kwargs)

    def test_iteration_helpers_discover_entity_and_ingress_route_names(self):
        model = inventory_model(
            hosts={
                "wintermute": {
                    "ingress": {
                        "proxmox_web_ui": {
                            "enabled": True,
                        },
                    },
                },
                "straylight": {},
            },
            vms={"media01": {}, "dns01": {}},
            services={
                "photos": {"ingress": {"enabled": True}},
                "private": {"ingress": {"enabled": False}},
            },
        )

        graph = InventoryEntityGraph(model)

        self.assertEqual(("wintermute", "straylight"), graph.host_names())
        self.assertEqual(("media01", "dns01"), graph.vm_names())
        self.assertEqual(("photos", "private"), graph.service_names())
        self.assertEqual(("photos",), graph.ingress_enabled_service_names())
        self.assertEqual(("wintermute",), graph.host_ingress_route_names())


if __name__ == "__main__":
    unittest.main()
