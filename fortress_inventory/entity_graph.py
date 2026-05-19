"""Inventory Entity Graph queries over the loaded Inventory model."""

from dataclasses import dataclass
from ipaddress import ip_interface, ip_network
from pathlib import PurePosixPath

from fortress_inventory.service_runtime_intent import analyze_service_runtime_intent


class InventoryEntityGraphError(ValueError):
    pass


@dataclass(frozen=True)
class VmMountFact:
    vm_name: str
    name: str
    dataset_name: str | None
    protocol: str | None
    mount_point: str | None
    access: str | None


@dataclass(frozen=True)
class MountDatasetFact:
    vm_name: str
    mount_name: str
    dataset_name: str
    nas_endpoint_name: str | None
    path: str | None
    lifecycle: str
    owner: dict | None


@dataclass(frozen=True)
class DesiredNfsShareInput:
    dataset_name: str
    path: str | None
    protocol: str
    access: str
    lifecycle: str
    client_addresses: tuple[str, ...]


@dataclass(frozen=True)
class ServiceShareBackedVolumeFact:
    service_name: str
    vm_name: str
    container_name: str | None
    mount_name: str
    dataset_name: str | None
    source: str | None
    container_path: str | None
    access: str | None
    mount_point: str | None
    source_path: str | None


@dataclass(frozen=True)
class HostBridgeFact:
    name: str | None
    cidr: str | None
    gateway: str | None


@dataclass(frozen=True)
class InstrumentedVmFact:
    vm_name: str
    static_ipv4_address: str | None


@dataclass(frozen=True)
class ServiceTelemetryTargetFact:
    service_name: str
    vm_name: str
    vm_static_ipv4_address: str | None
    name: str
    target_type: str
    published_port: int
    scheme: str
    path: str


@dataclass(frozen=True)
class ObservabilityViewIntent:
    view_id: str
    entity_kind: str
    entity_name: str
    view_kind: str
    profile: str | None


@dataclass(frozen=True)
class ServiceLaunchIntent:
    service_name: str
    backend_vm_name: str
    requires_ingress_regeneration: bool


@dataclass(frozen=True)
class ServiceGroupLaunchIntent:
    service_group_name: str
    backend_vm_name: str
    service_names: tuple[str, ...]
    requires_ingress_regeneration: bool


@dataclass(frozen=True)
class HostUpdateImpactedVm:
    vm_name: str
    vmid: int


@dataclass(frozen=True)
class HostUpdateRebootImpact:
    host_name: str
    ordinary_vms: tuple[HostUpdateImpactedVm, ...]
    resident_service_names: tuple[str, ...]


@dataclass(frozen=True)
class VmUpdateRebootImpact:
    vm_name: str
    resident_service_names: tuple[str, ...]


@dataclass(frozen=True)
class VmLifecycleSelectedHostFacts:
    vm_name: str
    placement_host_name: str
    provider_host_names: tuple[str, ...]


@dataclass(frozen=True)
class TemplateVerificationIntent:
    host_name: str
    template_name: str
    management_address: str
    vmid: int
    hardware: dict
    storage: str
    static_address: str
    bridge: HostBridgeFact


@dataclass(frozen=True)
class TemplateLineageVmFact:
    vm_name: str
    vmid: int | None
    placement_host_name: str | None
    template_name: str


@dataclass(frozen=True)
class AcceptanceEphemeralDatasetFact:
    name: str
    nas_endpoint_name: str
    path: str
    lifecycle: str


@dataclass(frozen=True)
class AcceptanceOperationalVmFact:
    role: str
    name: str | None
    vmid: int | None
    static_address: str
    client_address: str
    bridge: HostBridgeFact


@dataclass(frozen=True)
class AcceptancePolicyIntent:
    policy_name: str
    host_name: str
    template_name: str
    nas_endpoint_name: str
    nas_endpoint: dict
    hardware: dict
    storage: str
    mount: dict
    dataset: AcceptanceEphemeralDatasetFact
    vms: tuple[AcceptanceOperationalVmFact, ...]


class InventoryEntityGraph:
    def __init__(self, model):
        self._model = model

    def host_names(self):
        return tuple(self._model.hosts)

    def vm_names(self):
        return tuple(self._model.vms)

    def service_names(self):
        return tuple(self._model.services)

    def ingress_enabled_service_names(self):
        return tuple(
            service_name
            for service_name, service in self._model.services.items()
            if service.get("ingress", {}).get("enabled")
        )

    def host_ingress_route_names(self):
        return tuple(
            host_name
            for host_name, host in self._model.hosts.items()
            if host.get("ingress", {}).get("proxmox_web_ui", {}).get("enabled")
        )

    def service_backend_vm_name(self, service_name):
        return self._service_backend(service_name).get("vm")

    def service_backend_port(self, service_name):
        return self._service_backend(service_name).get("port")

    def instrumented_vm_facts(self):
        return tuple(
            InstrumentedVmFact(
                vm_name=vm_name,
                static_ipv4_address=self.vm_static_ipv4_address(vm_name),
            )
            for vm_name, vm in sorted(self._model.vms.items())
            if _is_ordinary_vm(vm) and (vm.get("instrumentation") or {}).get("enabled", True) is True
        )

    def service_telemetry_target_facts(self):
        intent = analyze_service_runtime_intent(self._model)
        return tuple(
            ServiceTelemetryTargetFact(
                service_name=target.service_name,
                vm_name=target.vm_name,
                vm_static_ipv4_address=self.vm_static_ipv4_address(target.vm_name),
                name=target.name,
                target_type=target.target_type,
                published_port=target.published_port,
                scheme=target.scheme,
                path=target.path,
            )
            for target in intent.telemetry_targets
        )

    def observability_view_intents(self, excluded_vm_names=()):
        return self.vm_observability_view_intents(
            excluded_vm_names=excluded_vm_names
        ) + self.service_observability_view_intents(excluded_vm_names=excluded_vm_names)

    def vm_observability_view_intents(self, excluded_vm_names=()):
        excluded_vm_names = frozenset(excluded_vm_names)
        return tuple(
            ObservabilityViewIntent(
                view_id=f"vm:{vm.vm_name}:vm_baseline",
                entity_kind="vm",
                entity_name=vm.vm_name,
                view_kind="vm_baseline",
                profile=None,
            )
            for vm in self.instrumented_vm_facts()
            if vm.vm_name not in excluded_vm_names
        )

    def service_observability_view_intents(self, excluded_vm_names=()):
        excluded_vm_names = frozenset(excluded_vm_names)
        return tuple(
            ObservabilityViewIntent(
                view_id=f"service:{service_name}:{request['profile']}",
                entity_kind="service",
                entity_name=service_name,
                view_kind="service_profile",
                profile=request["profile"],
            )
            for service_name, service in sorted(self._model.services.items())
            for request in (service.get("instrumentation") or {}).get("observability_views", []) or []
            if isinstance(request, dict) and request.get("profile")
            if self.service_backend_vm_name(service_name) not in excluded_vm_names
        )

    def service_launch_intent(self, service_name):
        service = self._model.services.get(service_name)
        if not service:
            return None
        backend_vm_name = self.service_backend_vm_name(service_name)
        if not backend_vm_name:
            raise InventoryEntityGraphError(f"Service {service_name} has no backend.vm")
        if backend_vm_name not in self._model.vms:
            raise InventoryEntityGraphError(
                f"Service {service_name} references missing Backend VM {backend_vm_name}"
            )
        return ServiceLaunchIntent(
            service_name=service_name,
            backend_vm_name=backend_vm_name,
            requires_ingress_regeneration=service.get("ingress", {}).get("enabled") is True,
        )

    def service_group_launch_intent(self, service_group_name):
        member_service_names = tuple(
            service_name
            for service_name, service in self._model.services.items()
            if service.get("service_group") == service_group_name
        )
        if not member_service_names:
            raise InventoryEntityGraphError(f"Service Group {service_group_name} is not declared")

        declaration = None
        backend_vm_name = None
        for vm_name, vm in self._model.vms.items():
            for group in vm.get("launchable_service_groups", []) or []:
                if group.get("name") == service_group_name:
                    declaration = group
                    backend_vm_name = vm_name
                    break
            if declaration is not None:
                break

        if declaration is None:
            raise InventoryEntityGraphError(
                f"Service Group {service_group_name} is not launchable; "
                "no Backend VM declares launch metadata"
            )

        service_names = tuple(declaration.get("launch_order", []) or [])
        for service_name in member_service_names:
            service_backend_vm_name = self._service_backend(service_name).get("vm")
            if not service_backend_vm_name:
                raise InventoryEntityGraphError(
                    f"Service Group Launch {service_group_name} Service {service_name} has no Backend VM"
                )
            if service_backend_vm_name not in self._model.vms:
                raise InventoryEntityGraphError(
                    f"Service Group Launch {service_group_name} Service {service_name} "
                    f"references missing Backend VM {service_backend_vm_name}"
                )
            if service_backend_vm_name != backend_vm_name:
                raise InventoryEntityGraphError(
                    f"Service Group Launch {service_group_name} requires shared Backend VM {backend_vm_name}; "
                    f"Service {service_name} uses {service_backend_vm_name}"
                )
        for service_name in service_names:
            service = self._model.services.get(service_name)
            if not service:
                raise InventoryEntityGraphError(
                    f"Service Group Launch {service_group_name} references missing Service {service_name}"
                )
            if service.get("service_group") != service_group_name:
                raise InventoryEntityGraphError(
                    f"Service Group Launch {service_group_name} includes Service {service_name}, "
                    f"which does not declare Service Group {service_group_name}"
                )
        omitted_service_names = sorted(set(member_service_names) - set(service_names))
        if omitted_service_names:
            raise InventoryEntityGraphError(
                f"Service Group Launch {service_group_name} omits Service "
                f"{omitted_service_names[0]} from Launch Order"
            )
        return ServiceGroupLaunchIntent(
            service_group_name=service_group_name,
            backend_vm_name=backend_vm_name,
            service_names=service_names,
            requires_ingress_regeneration=any(
                (self._model.services.get(service_name) or {}).get("ingress", {}).get("enabled") is True
                for service_name in service_names
            ),
        )

    def host_update_reboot_impact(self, host_name):
        if host_name not in self._model.hosts:
            return None

        impacted_vms = []
        for vm_name, vm in self._model.vms.items():
            if self.vm_placement_host_name(vm_name) != host_name:
                continue
            vmid = vm.get("vmid")
            if vmid is None:
                raise InventoryEntityGraphError(f"VM {vm_name} has no vmid for Host Update reboot interruption")
            impacted_vms.append(HostUpdateImpactedVm(vm_name=vm_name, vmid=vmid))

        impacted_vm_names = {vm.vm_name for vm in impacted_vms}
        resident_services = []
        for service_name in self._model.services:
            backend_vm_name = self.service_backend_vm_name(service_name)
            if backend_vm_name in impacted_vm_names:
                resident_services.append(service_name)

        return HostUpdateRebootImpact(
            host_name=host_name,
            ordinary_vms=tuple(sorted(impacted_vms, key=lambda vm: vm.vm_name)),
            resident_service_names=tuple(sorted(resident_services)),
        )

    def vm_update_reboot_impact(self, vm_name):
        if vm_name not in self._model.vms:
            return None

        resident_services = []
        for service_name in self._model.services:
            backend_vm_name = self.service_backend_vm_name(service_name)
            if backend_vm_name == vm_name:
                resident_services.append(service_name)

        return VmUpdateRebootImpact(
            vm_name=vm_name,
            resident_service_names=tuple(sorted(resident_services)),
        )

    def _service_backend(self, service_name):
        service = self._model.services.get(service_name)
        if not service:
            return {}
        backend = service.get("backend") or {}
        if not isinstance(backend, dict):
            raise InventoryEntityGraphError(f"Service {service_name} must declare one singular Backend")
        return backend

    def vm_mount(self, vm_name, mount_name):
        vm = self._model.vms.get(vm_name)
        if not vm:
            return None
        matches = []
        for mount in vm.get("mounts", []) or []:
            if mount.get("name") == mount_name:
                matches.append(mount)
        if len(matches) > 1:
            raise InventoryEntityGraphError(f"VM {vm_name} declares duplicate Mount Name {mount_name}")
        if not matches:
            return None
        mount = matches[0]
        return VmMountFact(
            vm_name=vm_name,
            name=mount_name,
            dataset_name=mount.get("dataset"),
            protocol=mount.get("protocol"),
            mount_point=mount.get("mount_point"),
            access=mount.get("access"),
        )

    def vm_mount_dataset_facts(self, vm_name, mount_name):
        mount = self.vm_mount(vm_name, mount_name)
        if mount is None:
            return None
        dataset = self._dataset_by_declared_name(mount.dataset_name)
        if not dataset:
            raise InventoryEntityGraphError(
                f"VM {vm_name} Mount {mount_name} references missing Dataset {mount.dataset_name}"
            )
        return MountDatasetFact(
            vm_name=vm_name,
            mount_name=mount_name,
            dataset_name=mount.dataset_name,
            nas_endpoint_name=dataset.get("nas"),
            path=dataset.get("path"),
            lifecycle=dataset.get("lifecycle", "adopted"),
            owner=dataset.get("owner"),
        )

    def desired_nfs_share_inputs(self, include_ephemeral_datasets=False, dataset_names=None):
        dataset_names = set(dataset_names) if dataset_names is not None else None
        grouped = {}
        for vm_name, vm in self._model.vms.items():
            client_addresses = self.vm_nfs_client_addresses(vm_name)
            for mount in vm.get("mounts", []) or []:
                if mount.get("protocol") != "nfs" or not mount.get("name"):
                    continue
                if dataset_names is not None and mount.get("dataset") not in dataset_names:
                    continue
                dataset_facts = self.vm_mount_dataset_facts(vm_name, mount["name"])
                if (
                    dataset_facts.lifecycle != "adopted"
                    and not include_ephemeral_datasets
                ):
                    continue
                key = (
                    dataset_facts.dataset_name,
                    dataset_facts.path,
                    mount.get("protocol"),
                    mount.get("access"),
                    dataset_facts.lifecycle,
                )
                grouped.setdefault(key, set()).update(client_addresses)

        return tuple(
            DesiredNfsShareInput(
                dataset_name=dataset_name,
                path=path,
                protocol=protocol,
                access=access,
                lifecycle=lifecycle,
                client_addresses=tuple(sorted(clients)),
            )
            for (dataset_name, path, protocol, access, lifecycle), clients in sorted(grouped.items())
        )

    def service_share_backed_volumes(self, service_name):
        service = self._model.services.get(service_name)
        if not service:
            return ()
        vm_name = self.service_backend_vm_name(service_name)
        if not vm_name:
            return ()
        if vm_name not in self._model.vms:
            raise InventoryEntityGraphError(
                f"Service {service_name} references missing Backend VM {vm_name}"
            )

        volumes = []
        for container in service.get("deploy", {}).get("containers", []) or []:
            for volume in container.get("volumes", []) or []:
                mount_name = volume.get("mount")
                if not mount_name:
                    continue
                mount = self.vm_mount(vm_name, mount_name)
                if not mount:
                    raise InventoryEntityGraphError(
                        f"Service {service_name} Share-backed Volume references missing Mount Name "
                        f"{mount_name} on Backend VM {vm_name}"
                    )
                volumes.append(
                    ServiceShareBackedVolumeFact(
                        service_name=service_name,
                        vm_name=vm_name,
                        container_name=container.get("name"),
                        mount_name=mount_name,
                        dataset_name=mount.dataset_name,
                        source=volume.get("source"),
                        container_path=volume.get("container"),
                        access=volume.get("access", mount.access),
                        mount_point=mount.mount_point,
                        source_path=_share_backed_source_path(
                            mount.mount_point,
                            volume.get("source"),
                        ),
                    )
                )
        return tuple(volumes)

    def _dataset_by_declared_name(self, dataset_name):
        if not dataset_name:
            return None
        matches = [
            dataset
            for dataset in self._model.datasets.values()
            if dataset.get("name") == dataset_name
        ]
        if len(matches) > 1:
            raise InventoryEntityGraphError(
                f"Dataset name {dataset_name} is declared by multiple Dataset Entities"
            )
        if not matches:
            return None
        return matches[0]

    def vm_placement_host_name(self, vm_name):
        vm = self._model.vms.get(vm_name)
        if not vm:
            return None
        return (vm.get("placement") or {}).get("host")

    def vm_lifecycle_selected_host_facts(self, vm_name, provider_host_names=()):
        if vm_name not in self._model.vms:
            return None
        placement_host_name = self.vm_placement_host_name(vm_name)
        if not placement_host_name:
            raise InventoryEntityGraphError(f"VM {vm_name} has no placement.host")
        all_provider_hosts = {placement_host_name, *(provider_host_names or ())}
        missing_hosts = sorted(host for host in all_provider_hosts if host not in self._model.hosts)
        if missing_hosts:
            raise InventoryEntityGraphError(
                f"VM {vm_name} selected Host provider coverage references missing Host(s): "
                f"{', '.join(missing_hosts)}"
            )
        return VmLifecycleSelectedHostFacts(
            vm_name=vm_name,
            placement_host_name=placement_host_name,
            provider_host_names=tuple(sorted(all_provider_hosts)),
        )

    def vm_static_ipv4_addresses(self, vm_name):
        vm = self._model.vms.get(vm_name)
        if not vm:
            return ()
        addresses = []
        for interface_index, interface in enumerate(vm.get("network", {}).get("interfaces", []) or []):
            address = interface.get("address")
            if not address:
                continue
            try:
                parsed = ip_interface(address)
            except ValueError as error:
                raise InventoryEntityGraphError(
                    f"VM {vm_name} declares invalid network.interfaces[{interface_index}].address {address!r}"
                ) from error
            if parsed.version == 4:
                addresses.append(str(parsed.ip))
        return tuple(addresses)

    def vm_nfs_client_addresses(self, vm_name):
        return self.vm_static_ipv4_addresses(vm_name)

    def vm_static_ipv4_address(self, vm_name):
        addresses = self.vm_static_ipv4_addresses(vm_name)
        if not addresses:
            return None
        if len(addresses) > 1:
            raise InventoryEntityGraphError(f"VM {vm_name} must declare at most one static IPv4 address")
        return addresses[0]

    def host_management_ipv4_address(self, host_name):
        host = self._model.hosts.get(host_name)
        if not host:
            return None
        address = host.get("network", {}).get("management_address")
        if not address:
            return None
        try:
            parsed = ip_interface(address)
        except ValueError as error:
            raise InventoryEntityGraphError(
                f"Host {host_name} must declare network.management_address as an IPv4 address"
            ) from error
        if parsed.version != 4:
            raise InventoryEntityGraphError(
                f"Host {host_name} must declare network.management_address as an IPv4 address"
            )
        return str(parsed.ip)

    def host_bridge_name_matching_address(self, host_name, address):
        bridge = self.host_bridge_matching_address(host_name, address)
        if bridge is None:
            return None
        return bridge.name

    def host_bridge_matching_address(self, host_name, address):
        host = self._model.hosts.get(host_name)
        if not host:
            return None
        try:
            parsed_address = ip_interface(address)
        except ValueError as error:
            raise InventoryEntityGraphError(
                f"Host {host_name} bridge lookup address must be an IPv4 address"
            ) from error
        if parsed_address.version != 4:
            raise InventoryEntityGraphError(
                f"Host {host_name} bridge lookup address must be an IPv4 address"
            )
        matches = []
        for bridge in host.get("network", {}).get("bridges", []) or []:
            cidr = bridge.get("cidr")
            if not cidr:
                continue
            try:
                network = ip_network(cidr, strict=False)
            except ValueError as error:
                raise InventoryEntityGraphError(
                    f"Host {host_name} bridge {bridge.get('name')} declares invalid cidr {cidr!r}"
                ) from error
            if parsed_address.ip in network:
                matches.append(bridge)
        if len(matches) > 1:
            raise InventoryEntityGraphError(
                f"Host {host_name} address {address} matches multiple bridge CIDRs: "
                f"{', '.join(str(bridge.get('name')) for bridge in matches)}"
            )
        if not matches:
            return None
        bridge = matches[0]
        return HostBridgeFact(
            name=bridge.get("name"),
            cidr=bridge.get("cidr"),
            gateway=bridge.get("gateway"),
        )

    def template_verification_intent(self, host_name, template_name):
        host = self._model.hosts.get(host_name)
        if not host:
            return None
        if template_name not in self._model.templates:
            return None
        if template_name not in (host.get("proxmox", {}).get("templates", []) or []):
            raise InventoryEntityGraphError(
                f"Host {host_name} does not declare Template {template_name} under proxmox.templates"
            )

        policy = self._model.template_verification_policy
        storage = (policy.get("storage_by_host", {}) or {}).get(host_name)
        if not storage:
            raise InventoryEntityGraphError(
                f"Template Verification Policy has no storage_by_host entry for Host {host_name}"
            )
        static_address = (policy.get("address_by_host", {}) or {}).get(host_name)
        if not static_address:
            raise InventoryEntityGraphError(
                f"Template Verification Policy has no address_by_host entry for Host {host_name}"
            )
        management_address = self.host_management_ipv4_address(host_name)
        if not management_address:
            raise InventoryEntityGraphError(
                f"Host {host_name} has no network.management_address for Template Verification"
            )
        bridge = self.host_bridge_matching_address(host_name, static_address)
        if not bridge:
            raise InventoryEntityGraphError(
                f"Template Verification VM address {static_address} must match a Host bridge CIDR"
            )
        if not bridge.gateway:
            raise InventoryEntityGraphError(
                f"Host {host_name} bridge {bridge.name} has no gateway for Template Verification VM"
            )
        return TemplateVerificationIntent(
            host_name=host_name,
            template_name=template_name,
            management_address=management_address,
            vmid=policy.get("vmid"),
            hardware=policy.get("hardware") or {},
            storage=storage,
            static_address=static_address,
            bridge=bridge,
        )

    def host_names_declaring_template(self, template_name):
        return tuple(
            host_name
            for host_name, host in sorted(self._model.hosts.items())
            if template_name in (host.get("proxmox", {}).get("templates", []) or [])
        )

    def template_lineage_vms(self, template_name):
        return tuple(
            TemplateLineageVmFact(
                vm_name=vm_name,
                vmid=vm.get("vmid"),
                placement_host_name=(vm.get("placement") or {}).get("host"),
                template_name=template_name,
            )
            for vm_name, vm in sorted(self._model.vms.items())
            if (vm.get("source") or {}).get("template") == template_name
        )

    def acceptance_policy_intent(self, policy_name, host_name, template_name, nas_endpoint_name):
        if policy_name not in self._model.acceptance_policies:
            raise InventoryEntityGraphError(
                f"Acceptance Policy {policy_name!r} is not declared"
            )
        policy = self._model.acceptance_policies[policy_name]
        if host_name not in self._model.hosts:
            raise InventoryEntityGraphError(f"Host {host_name!r} is not declared")
        host = self._model.hosts[host_name]
        if template_name not in self._model.templates:
            raise InventoryEntityGraphError(f"Template {template_name!r} is not declared")
        if nas_endpoint_name not in self._model.nas_endpoints:
            raise InventoryEntityGraphError(f"NAS Endpoint {nas_endpoint_name!r} is not declared")
        if template_name not in (host.get("proxmox", {}).get("templates", []) or []):
            raise InventoryEntityGraphError(
                f"Host {host_name} does not declare Template {template_name} under proxmox.templates"
            )

        storage = (policy.get("storage_by_host", {}) or {}).get(host_name)
        if not storage:
            raise InventoryEntityGraphError(
                f"Acceptance Policy {policy_name} has no storage_by_host entry for Host {host_name}"
            )
        mount = policy.get("mount") or {}
        dataset_name = policy.get("dataset")
        if not dataset_name:
            raise InventoryEntityGraphError(f"Acceptance Policy {policy_name} has no dataset")
        mount_name = mount.get("name")
        if not mount_name:
            raise InventoryEntityGraphError(f"Acceptance Policy {policy_name} has no mount.name")

        vms = []
        for role, declaration in (policy.get("vms") or {}).items():
            static_address = (declaration.get("address_by_host", {}) or {}).get(host_name)
            if not static_address:
                raise InventoryEntityGraphError(
                    f"Acceptance Policy {policy_name} has no {role} address_by_host entry for Host {host_name}"
                )
            try:
                parsed_address = ip_interface(static_address)
            except ValueError as error:
                raise InventoryEntityGraphError(
                    f"Acceptance Policy {policy_name} {role} VM declares invalid address {static_address!r}"
                ) from error
            if parsed_address.version != 4:
                raise InventoryEntityGraphError(
                    f"Acceptance Policy {policy_name} {role} VM must declare an IPv4 address"
                )
            bridge = self.host_bridge_matching_address(host_name, static_address)
            if not bridge:
                raise InventoryEntityGraphError(
                    f"{role} VM address {static_address} must match a Host bridge CIDR"
                )
            if not bridge.gateway:
                raise InventoryEntityGraphError(
                    f"Host {host_name} bridge {bridge.name} has no gateway for generated Acceptance VM"
                )
            vms.append(
                AcceptanceOperationalVmFact(
                    role=role,
                    name=declaration.get("name"),
                    vmid=declaration.get("vmid"),
                    static_address=static_address,
                    client_address=str(parsed_address.ip),
                    bridge=bridge,
                )
            )

        return AcceptancePolicyIntent(
            policy_name=policy_name,
            host_name=host_name,
            template_name=template_name,
            nas_endpoint_name=nas_endpoint_name,
            nas_endpoint=self._model.nas_endpoints[nas_endpoint_name],
            hardware=policy.get("hardware") or {},
            storage=storage,
            mount=mount,
            dataset=AcceptanceEphemeralDatasetFact(
                name=dataset_name,
                nas_endpoint_name=nas_endpoint_name,
                path=f"/mnt/tank/fortress-acceptance/{mount_name}",
                lifecycle="ephemeral",
            ),
            vms=tuple(vms),
        )


def _share_backed_source_path(mount_point, source):
    if not mount_point or source in (None, "/"):
        return mount_point
    return str(PurePosixPath(mount_point) / source)


def _is_ordinary_vm(vm):
    return (vm.get("lifecycle") or {}).get("kind", "ordinary") == "ordinary"
