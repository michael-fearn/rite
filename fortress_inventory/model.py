from dataclasses import dataclass
from pathlib import Path

from .simple_yaml import load_yaml


@dataclass(frozen=True)
class InventoryModel:
    hosts: dict
    vms: dict
    services: dict
    datasets: dict
    nas_endpoints: dict
    templates: dict
    template_verification_policy: dict
    globals: dict


def load_inventory_tree(root):
    root = Path(root)
    inventory_root = root / "inventory"
    return InventoryModel(
        hosts=_load_entity_dir(inventory_root / "hosts"),
        vms=_load_entity_dir(inventory_root / "vms"),
        services=_load_entity_dir(inventory_root / "services"),
        datasets=_load_entity_dir(inventory_root / "datasets"),
        nas_endpoints=_load_entity_dir(inventory_root / "nas"),
        templates=_load_entity_dir(inventory_root / "templates"),
        template_verification_policy=_load_optional_yaml(inventory_root / "template-verification-policy.yaml"),
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
