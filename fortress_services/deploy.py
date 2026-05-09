from pathlib import PurePosixPath


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


def service_secret_key(secret):
    reference = secret["secret"]
    if reference.startswith("secrets."):
        return reference.split(".", 1)[1]
    return reference
