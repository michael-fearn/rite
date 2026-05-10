from pathlib import PurePosixPath

from fortress_services.quadlet import render_quadlet_service


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
    seen = set()
    for container in service.get("deploy", {}).get("containers", []) or []:
        for secret in container.get("secrets", []) or []:
            secret_key = service_secret_key(secret)
            if secret_key in seen:
                continue
            seen.add(secret_key)
            installations.append(
                {
                    "podman_name": f"fortress_{service['name']}_{secret_key}",
                    "sops_extract": f'["secrets"]["{secret_key}"]',
                }
            )
    return installations


def quadlet_deploy_vars(service, vm, inventory_root=None):
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
        "fortress_owned_quadlet_prune_paths": [
            artifact.path
            for artifact in rendered.artifacts
            if artifact.filename.startswith(f"fortress-{service['name']}-")
        ],
        "fortress_service_secret_prefix": f"fortress_{service['name']}_",
    }


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
