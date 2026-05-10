from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath


QUADLET_SYSTEM_PATH = "/etc/containers/systemd"
ADDITIVE_FRAGMENT_KEYS = {
    ("Unit", "Requires"),
    ("Unit", "After"),
    ("Unit", "Wants"),
}
RESERVED_FRAGMENT_KEYS = {
    ("Container", "AutoUpdate"),
    ("Container", "Secret"),
}
RESERVED_FRAGMENT_SECTIONS = {"Install"}


@dataclass(frozen=True)
class QuadletArtifact:
    filename: str
    content: str

    @property
    def path(self):
        return f"{QUADLET_SYSTEM_PATH}/{self.filename}"


@dataclass(frozen=True)
class ServiceDataDirectory:
    path: str
    uid: int | None = None
    gid: int | None = None


@dataclass(frozen=True)
class RenderedQuadletService:
    artifacts: tuple[QuadletArtifact, ...]
    service_data_directories: tuple[ServiceDataDirectory, ...] = ()

    @property
    def artifacts_by_filename(self):
        return {artifact.filename: artifact for artifact in self.artifacts}


def render_quadlet_service(service, vm, inventory_root=None):
    network_name = _service_network_name(service)
    fragments = _quadlet_fragments(service, inventory_root)
    artifacts = [
        _artifact_with_fragment(
            filename=f"{network_name}.network",
            content="\n".join(
                [
                    "[Network]",
                    f"NetworkName={network_name}",
                    "",
                ]
            ),
            fragment_content=fragments.get("network.network"),
        )
    ]
    for container in service["deploy"]["containers"]:
        runtime_name = _container_runtime_name(service, container)
        artifacts.append(
            _artifact_with_fragment(
                filename=f"{runtime_name}.container",
                content=render_quadlet_container(service, vm, container),
                fragment_content=fragments.get(f"{container['name']}.container"),
            )
        )
    return RenderedQuadletService(
        artifacts=tuple(artifacts),
        service_data_directories=tuple(_service_data_directories(service)),
    )


def render_quadlet_container(service, vm, container):
    mount_by_name = {
        mount.get("name"): mount
        for mount in vm.get("mounts", []) or []
        if mount.get("name")
    }
    required_units = []
    ordered_after_units = []
    bound_units = []
    for dependency in container.get("depends_on", []) or []:
        dependency_unit = f"fortress-{service['name']}-{dependency}.service"
        required_units.append(dependency_unit)
        ordered_after_units.append(dependency_unit)
        bound_units.append(dependency_unit)
    lines = [
        "[Unit]",
        f"Description=Fortress Service {service['name']} container {container['name']}",
        "",
        "[Container]",
        f"ContainerName={_container_runtime_name(service, container)}",
        f"Image={container['image']}",
        f"Network={_service_network_name(service)}",
        f"NetworkAlias={container['name']}",
    ]

    for published_port in container.get("published_ports", []) or []:
        lines.append(f"PublishPort={_published_port(published_port)}")

    for name, value in (container.get("env") or {}).items():
        lines.append(f"Environment={name}={_quadlet_env_value(value)}")

    for secret in container.get("secrets", []) or []:
        secret_name = _service_secret_name(service, secret)
        lines.append(f"Secret={secret_name}")
        lines.append(f"Environment={secret['env']}=/run/secrets/{secret_name}")

    for volume in container.get("volumes", []) or []:
        if volume.get("mount"):
            mount = mount_by_name[volume["mount"]]
            mount_unit = systemd_mount_unit_name(mount["mount_point"])
            required_units.append(mount_unit)
            ordered_after_units.append(mount_unit)
            lines.append(
                f"Volume={_share_backed_volume_source(mount, volume)}:"
                f"{volume['container']}:{_volume_mode(volume, mount)}"
            )
        else:
            lines.append(
                f"Volume={_service_owned_volume_source(service, volume)}:"
                f"{volume['container']}:{_volume_mode(volume)}"
            )

    unit_lines = []
    if required_units:
        unit_lines.append(f"Requires={_unique_units(required_units)}")
    if ordered_after_units:
        unit_lines.append(f"After={_unique_units(ordered_after_units)}")
    if bound_units:
        unit_lines.append(f"BindsTo={_unique_units(bound_units)}")
    if unit_lines:
        lines[2:2] = unit_lines

    return "\n".join(lines) + "\n"


def systemd_mount_unit_name(mount_point):
    normalized = "/".join(part for part in str(mount_point).split("/") if part)
    if not normalized:
        return "-.mount"

    escaped = []
    at_start = True
    for char in normalized:
        if char == "/":
            escaped.append("-")
            at_start = True
            continue
        escaped.append(_escape_systemd_path_char(char, at_start))
        at_start = False
    return f"{''.join(escaped)}.mount"


def _escape_systemd_path_char(char, at_start):
    allowed = char.isalnum() or char in ":_."
    if allowed and not (at_start and char == "."):
        return char
    return "".join(f"\\x{byte:02x}" for byte in char.encode())


def _service_network_name(service):
    if service.get("service_group"):
        return f"fortress-group-{service['service_group']}"
    return f"fortress-{service['name']}"


def _container_runtime_name(service, container):
    return f"fortress-{service['name']}-{container['name']}"


def _published_port(published_port):
    bind = published_port.get("bind")
    host = published_port.get("host", published_port["container"])
    container = published_port["container"]
    protocol = published_port.get("protocol", "tcp")
    protocol_suffix = "tcp,udp" if protocol == "tcp_udp" else protocol
    if bind:
        return f"{bind}:{host}:{container}/{protocol_suffix}"
    return f"{host}:{container}/{protocol_suffix}"


def _quadlet_env_value(value):
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _service_secret_name(service, secret):
    return f"fortress_{service['name']}_{_service_secret_key(secret)}"


def _service_secret_key(secret):
    reference = secret["secret"]
    if not reference.startswith("secrets."):
        return reference
    return reference.split(".", 1)[1]


def _unique_units(units):
    return " ".join(dict.fromkeys(units))


def _share_backed_volume_source(mount, volume):
    if volume["source"] == "/":
        return mount["mount_point"]
    return str(PurePosixPath(mount["mount_point"]) / volume["source"])


def _service_owned_volume_source(service, volume):
    return str(PurePosixPath("/srv/services") / service["name"] / volume["service_path"])


def _volume_mode(volume, mount=None):
    access = volume.get("access")
    if access is None and mount is not None:
        access = mount.get("access")
    return "ro" if access == "read_only" else "rw"


def _service_data_directories(service):
    owner = service.get("service_data_owner") or {}
    directories = []
    seen = set()
    for container in service.get("deploy", {}).get("containers", []) or []:
        for volume in container.get("volumes", []) or []:
            if "service_path" not in volume:
                continue
            path = _service_owned_volume_source(service, volume)
            if path in seen:
                continue
            seen.add(path)
            directories.append(
                ServiceDataDirectory(
                    path=path,
                    uid=owner.get("uid"),
                    gid=owner.get("gid"),
                )
            )
    return directories


def _quadlet_fragments(service, inventory_root):
    if inventory_root is None:
        return {}
    fragment_dir = Path(inventory_root) / "services" / f"{service['name']}.quadlet.d"
    if not fragment_dir.is_dir():
        return {}
    allowed_names = {
        f"{container['name']}.container"
        for container in service.get("deploy", {}).get("containers", []) or []
    }
    allowed_names.add("network.network")
    fragments = {}
    for fragment_path in sorted(fragment_dir.iterdir()):
        if not fragment_path.is_file():
            continue
        if fragment_path.name not in allowed_names:
            raise ValueError(
                f"unknown Quadlet Fragment for Service {service['name']}: {fragment_path.name}"
            )
        fragments[fragment_path.name] = fragment_path.read_text()
    return fragments


def _artifact_with_fragment(filename, content, fragment_content=None):
    if fragment_content is not None:
        content = _merge_quadlet_fragment(content, fragment_content)
    return QuadletArtifact(filename=filename, content=content)


def _merge_quadlet_fragment(generated_content, fragment_content):
    generated_keys = _quadlet_keys(generated_content)
    generated_environment_names = _quadlet_environment_names(generated_content)
    insertions = _quadlet_entries(fragment_content)
    additive_values = {}
    additions_by_section = {}
    for section, key, value in insertions:
        if section in RESERVED_FRAGMENT_SECTIONS or (section, key) in RESERVED_FRAGMENT_KEYS:
            raise ValueError(f"Quadlet Fragment uses reserved fortress-owned key: {section}.{key}")
        if (section, key) in generated_keys:
            if (section, key) == ("Container", "Environment"):
                environment_name = _environment_name(value)
                if environment_name in generated_environment_names:
                    raise ValueError(
                        "Quadlet Fragment cannot override fortress-owned environment variable: "
                        f"{environment_name}"
                    )
                additions_by_section.setdefault(section, []).append(f"{key}={value}")
                continue
            if (section, key) in ADDITIVE_FRAGMENT_KEYS:
                additive_values.setdefault((section, key), []).extend(value.split())
                continue
            raise ValueError(f"Quadlet Fragment cannot override fortress-owned key: {section}.{key}")
        additions_by_section.setdefault(section, []).append(f"{key}={value}")

    lines = generated_content.splitlines()
    output = []
    seen_sections = set()
    current_section = None
    for line in lines:
        next_section = _section_name(line)
        if next_section is not None and current_section in additions_by_section:
            _append_section_additions(output, additions_by_section[current_section])
            seen_sections.add(current_section)
        output.append(_line_with_additive_values(current_section, line, additive_values))
        if next_section is not None:
            current_section = next_section
    if current_section in additions_by_section:
        _append_section_additions(output, additions_by_section[current_section])
        seen_sections.add(current_section)

    for section, additions in additions_by_section.items():
        if section in seen_sections:
            continue
        if output and output[-1] != "":
            output.append("")
        output.append(f"[{section}]")
        output.extend(additions)
    return "\n".join(output) + "\n"


def _append_section_additions(output, additions):
    had_section_separator = bool(output and output[-1] == "")
    if had_section_separator:
        output.pop()
    output.extend(additions)
    if had_section_separator:
        output.append("")


def _line_with_additive_values(section, line, additive_values):
    if section is None or "=" not in line:
        return line
    key, value = line.split("=", 1)
    values_to_add = additive_values.get((section, key.strip()))
    if not values_to_add:
        return line
    return f"{key}={_unique_units(value.split() + values_to_add)}"


def _quadlet_keys(content):
    return {(section, key) for section, key, _value in _quadlet_entries(content)}


def _quadlet_entries(content):
    entries = []
    section = None
    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        parsed_section = _section_name(line)
        if parsed_section is not None:
            section = parsed_section
            continue
        if "=" not in line or section is None:
            raise ValueError(f"invalid Quadlet Fragment INI syntax on line {line_number}")
        key, value = line.split("=", 1)
        entries.append((section, key.strip(), value.strip()))
    return entries


def _quadlet_environment_names(content):
    return {
        _environment_name(value)
        for section, key, value in _quadlet_entries(content)
        if (section, key) == ("Container", "Environment")
    }


def _environment_name(value):
    return value.split("=", 1)[0]


def _section_name(line):
    stripped = line.strip()
    if stripped.startswith("[") and stripped.endswith("]") and len(stripped) > 2:
        return stripped[1:-1]
    return None
