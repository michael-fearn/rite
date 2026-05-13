import json
import subprocess
from copy import deepcopy
from pathlib import Path
from pathlib import PurePosixPath

from fortress_services.quadlet import render_quadlet_service


REQUIRED_SERVICE_SECRET_FIELDS = ("created", "version", "value")


class ServiceSecretPreflightError(ValueError):
    pass


def share_backed_volume_subpaths(service, vm):
    mount_by_name = {
        mount.get("name"): mount
        for mount in vm.get("mounts", []) or []
        if mount.get("name")
    }
    subpaths = []
    for container in service.get("deploy", {}).get("containers", []) or []:
        for volume in container.get("volumes", []) or []:
            mount_name = volume.get("mount")
            source = volume.get("source")
            if not mount_name or source in (None, "/"):
                continue
            mount = mount_by_name[mount_name]
            subpaths.append(str(PurePosixPath(mount["mount_point"]) / source))
    return subpaths


def service_secret_installations(service):
    installations = []
    for secret_key in service_secret_keys(service):
        installations.append(
            {
                "podman_name": f"fortress_{service['name']}_{secret_key}",
                "sops_extract": _sops_extract_path("secrets", secret_key, "value"),
            }
        )
    return installations


def service_secret_keys(service):
    keys = []
    seen = set()
    for container in service.get("deploy", {}).get("containers", []) or []:
        for secret in container.get("secrets", []) or []:
            secret_key = service_secret_key(secret)
            if secret_key in seen:
                continue
            seen.add(secret_key)
            keys.append(secret_key)
    return keys


def preflight_service_secret_shape(service_name, service_sops_path, secret_keys):
    result = subprocess.run(
        ["sops", "--decrypt", str(service_sops_path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise ServiceSecretPreflightError(
            f"failed to decrypt Service Sibling SOPS File at {service_sops_path} "
            f"for Service {service_name}"
        )

    entries = _service_secret_entries(result.stdout)
    for secret_key in secret_keys:
        fields = entries.get(secret_key)
        if secret_key not in entries:
            raise ServiceSecretPreflightError(
                f"missing Service Secret secrets.{secret_key} in Service Sibling SOPS File "
                f"{service_sops_path}"
            )
        if fields is None:
            raise ServiceSecretPreflightError(
                f"Service Secret secrets.{secret_key} in {service_sops_path} must be a "
                "structured entry with created, version, and value fields; scalar legacy "
                "entries are not supported"
            )
        missing = [
            field
            for field in REQUIRED_SERVICE_SECRET_FIELDS
            if field not in fields
        ]
        if missing:
            raise ServiceSecretPreflightError(
                f"Service Secret secrets.{secret_key} in {service_sops_path} is missing "
                f"required field(s): {', '.join(missing)}"
            )


def quadlet_deploy_vars(service, vm, inventory_root=None):
    service = _service_with_deploy_capability_setup(service)
    rendered = render_quadlet_service(service, vm, inventory_root=inventory_root)
    start_units = service_start_units(service)
    network_units = quadlet_network_units(rendered.artifacts)
    return {
        "fortress_quadlet_artifacts": [
            {"filename": artifact.filename, "path": artifact.path, "content": artifact.content}
            for artifact in rendered.artifacts
        ],
        "fortress_service_data_directories": [
            service_data_directory_vars(directory)
            for directory in rendered.service_data_directories
        ],
        "fortress_service_network_units": network_units,
        "fortress_service_start_units": start_units,
        "fortress_service_stop_units": list(reversed(start_units)),
        "fortress_service_container_images": [
            container["image"]
            for container in service.get("deploy", {}).get("containers", []) or []
        ],
        "fortress_owned_quadlet_prune_paths": [
            artifact.path
            for artifact in rendered.artifacts
            if artifact.filename.startswith(f"fortress-{service['name']}-")
        ],
        "fortress_service_secret_prefix": f"fortress_{service['name']}_",
    }


def _service_with_deploy_capability_setup(service):
    if not _needs_pihole_dnsmasq_d_compatibility(service):
        return service
    service = deepcopy(service)
    for container in service.get("deploy", {}).get("containers", []) or []:
        if container.get("name") != "pihole":
            continue
        env = container.setdefault("env", {})
        env.setdefault("FTLCONF_misc_etc_dnsmasq_d", True)
        break
    return service


def _needs_pihole_dnsmasq_d_compatibility(service):
    dns = service.get("dns") or {}
    return dns.get("provider") == "pihole" and dns.get("ingress_records", {}).get("enabled") is True


def native_deploy_vars(service, globals_, inventory_root=None):
    deploy = service["deploy"]
    template_root = Path(inventory_root) / "services" / f"{service['name']}.native.d"
    apt_repo_name = deploy.get("apt_repo")
    apt_repo = None
    if apt_repo_name:
        apt_repo = dict((globals_.get("apt_repos") or {})[apt_repo_name])
        apt_repo["name"] = apt_repo_name
    return {
        "fortress_service_deploy_type": "native",
        "fortress_native_package": deploy["package"],
        "fortress_native_apt_repo": apt_repo,
        "fortress_native_systemd_unit": deploy["service_name"],
        "fortress_native_config_files": [
            {
                "src": str(template_root / config_file["template"]),
                "dest": config_file["dest"],
                "mode": config_file.get("mode", "0644"),
                "action": _native_config_change_action(config_file),
            }
            for config_file in deploy.get("config_files", []) or []
        ],
    }


def _native_config_change_action(config_file):
    if config_file.get("restart_on_change") is True:
        return "restart"
    return "reload"


def service_start_units(service):
    containers = {
        container["name"]: container
        for container in service.get("deploy", {}).get("containers", []) or []
    }
    ordered = []
    visiting = set()
    visited = set()

    def visit(container_name):
        if container_name in visited:
            return
        if container_name in visiting:
            raise ValueError(f"cycle in Container Dependency graph for Service {service['name']}")
        visiting.add(container_name)
        container = containers[container_name]
        for dependency in container.get("depends_on", []) or []:
            if dependency not in containers:
                raise ValueError(
                    f"unknown Container Dependency {dependency!r} for Service {service['name']}"
                )
            visit(dependency)
        visiting.remove(container_name)
        visited.add(container_name)
        ordered.append(fortress_container_unit(service, container_name))

    for container_name in containers:
        visit(container_name)
    return ordered


def quadlet_network_units(artifacts):
    return [
        f"{artifact.filename.removesuffix('.network')}-network.service"
        for artifact in artifacts
        if artifact.filename.endswith(".network")
    ]


def fortress_container_unit(service, container_name):
    return f"fortress-{service['name']}-{container_name}.service"


def service_data_directory_vars(directory):
    values = {"path": directory.path}
    if directory.uid is not None:
        values["uid"] = directory.uid
    if directory.gid is not None:
        values["gid"] = directory.gid
    return values


def service_secret_key(secret):
    reference = secret["secret"]
    if reference.startswith("secrets."):
        return reference.split(".", 1)[1]
    return reference


def _service_secret_entries(yaml_text):
    lines = _yaml_lines(yaml_text)
    for position, (indent, text) in enumerate(lines):
        key, raw_value = _yaml_mapping_entry(text)
        if indent == 0 and key == "secrets":
            if raw_value:
                return {}
            return _nested_service_secret_entries(lines, position, indent)
    return {}


def _nested_service_secret_entries(lines, start_position, parent_indent):
    entries = {}
    secret_indent = _next_child_indent(lines, start_position, parent_indent)
    if secret_indent is None:
        return entries

    position = start_position + 1
    while position < len(lines):
        indent, text = lines[position]
        if indent <= parent_indent:
            break
        if indent != secret_indent:
            position += 1
            continue
        key, raw_value = _yaml_mapping_entry(text)
        if key is None:
            position += 1
            continue
        if raw_value:
            entries[key] = _inline_mapping_fields(raw_value)
            position += 1
            continue

        field_indent = _next_child_indent(lines, position, secret_indent)
        fields = set()
        position += 1
        while position < len(lines):
            field_line_indent, field_text = lines[position]
            if field_line_indent <= secret_indent:
                break
            if field_indent is not None and field_line_indent == field_indent:
                field_key, _field_raw_value = _yaml_mapping_entry(field_text)
                if field_key is not None:
                    fields.add(field_key)
            position += 1
        entries[key] = fields
    return entries


def _yaml_lines(yaml_text):
    lines = []
    for raw_line in yaml_text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append((len(raw_line) - len(raw_line.lstrip(" ")), raw_line.lstrip(" ")))
    return lines


def _next_child_indent(lines, parent_position, parent_indent):
    for indent, _text in lines[parent_position + 1:]:
        if indent <= parent_indent:
            return None
        return indent
    return None


def _yaml_mapping_entry(text):
    if text.startswith("- ") or ":" not in text:
        return None, None
    key, raw_value = text.split(":", 1)
    key = key.strip().strip("\"'")
    if not key:
        return None, None
    return key, raw_value.strip()


def _inline_mapping_fields(raw_value):
    if not (raw_value.startswith("{") and raw_value.endswith("}")):
        return None
    fields = set()
    for part in raw_value[1:-1].split(","):
        key, _value = _yaml_mapping_entry(part.strip())
        if key is not None:
            fields.add(key)
    return fields


def _sops_extract_path(*parts):
    return "".join(f"[{json.dumps(part)}]" for part in parts)
