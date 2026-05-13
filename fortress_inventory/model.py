from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from .simple_yaml import load_yaml


@dataclass(frozen=True)
class InventoryModel:
    root: Path
    hosts: dict
    vms: dict
    services: dict
    datasets: dict
    nas_endpoints: dict
    templates: dict
    template_verification_policy: dict
    acceptance_policies: dict
    globals: dict


def load_inventory_tree(root):
    root = Path(root)
    inventory_root = root / "inventory"
    services = _load_entity_dir(inventory_root / "services")
    return InventoryModel(
        root=root,
        hosts=_load_entity_dir(inventory_root / "hosts"),
        vms=_load_entity_dir(inventory_root / "vms"),
        services=_default_services(services),
        datasets=_load_entity_dir(inventory_root / "datasets"),
        nas_endpoints=_load_entity_dir(inventory_root / "nas"),
        templates=_load_entity_dir(inventory_root / "templates"),
        template_verification_policy=_load_optional_yaml(inventory_root / "template-verification-policy.yaml"),
        acceptance_policies=_load_entity_dir(inventory_root / "acceptance"),
        globals=_load_optional_yaml(inventory_root / "group_vars" / "all.yaml"),
    )


def _load_entity_dir(path):
    entities = {}
    if not path.is_dir():
        return entities
    for yaml_path in sorted(path.glob("*.yaml")):
        if yaml_path.name.startswith("_") or yaml_path.name.endswith(".sops.yaml"):
            continue
        entities[yaml_path.stem] = load_yaml(yaml_path)
    return entities


def _load_optional_yaml(path):
    if not path.is_file():
        return {}
    return load_yaml(path)


def _default_services(services):
    return {
        service_name: _default_service(service)
        for service_name, service in services.items()
    }


def _default_service(service):
    service = deepcopy(service)
    ingress = dict(service.get("ingress") or {})
    if "ingress" not in service:
        ingress["enabled"] = False
    if ingress.get("enabled"):
        ingress.setdefault("exposure", "lan_only")
        ingress.setdefault("tls", "letsencrypt_dns")
        ingress.setdefault("auth", {"type": "none"})
    service["ingress"] = ingress
    for container in service.get("deploy", {}).get("containers", []) or []:
        for published_port in container.get("published_ports", []) or []:
            published_port.setdefault("bind", "127.0.0.1")
            published_port.setdefault("protocol", "tcp")
    return service
