from dataclasses import dataclass


@dataclass(frozen=True)
class NasReality:
    datasets: dict
    nfs_shares: list
    previous_mounts: list


class RecordingNasClient:
    def __init__(self):
        self.operations = []

    def create_dataset(self, dataset):
        self.operations.append({"method": "create_dataset", "dataset": dataset})

    def delete_dataset(self, dataset, path):
        self.operations.append({"method": "delete_dataset", "dataset": dataset, "path": path})

    def create_nfs_share(self, share):
        self.operations.append({"method": "create_nfs_share", "share": share})

    def update_nfs_share(self, share, desired):
        self.operations.append(
            {"method": "update_nfs_share", "share": share, "desired": desired}
        )

    def delete_nfs_share(self, share):
        self.operations.append({"method": "delete_nfs_share", "share": share})


def load_reality(data):
    datasets = {
        dataset.get("path"): dataset
        for dataset in data.get("datasets", []) or []
        if dataset.get("path")
    }
    return NasReality(
        datasets=datasets,
        nfs_shares=data.get("nfs_shares", []) or [],
        previous_mounts=data.get("previous_mounts", []) or [],
    )


def build_nas_reconcile_plan(
    inventory,
    reality,
    apply=False,
    client=None,
    confirm_disruptive_mount_changes=False,
    acceptance_ephemeral_datasets=False,
    destroy_ephemeral_datasets=False,
):
    dataset_findings = []
    dataset_write_actions = []
    for dataset in sorted(inventory.datasets.values(), key=lambda item: item.get("name", "")):
        lifecycle = dataset.get("lifecycle", "adopted")
        if lifecycle == "ephemeral":
            if acceptance_ephemeral_datasets:
                actions, findings = _ephemeral_dataset_write_actions_and_findings(
                    dataset,
                    reality,
                    destroy=destroy_ephemeral_datasets,
                )
                dataset_write_actions.extend(actions)
                dataset_findings.extend(findings)
            continue
        if lifecycle != "adopted":
            continue
        dataset_name = dataset.get("name")
        dataset_path = dataset.get("path")
        actual_dataset = reality.datasets.get(dataset_path)
        if not actual_dataset:
            dataset_findings.append(
                {
                    "code": "missing_dataset",
                    "dataset": dataset_name,
                    "path": dataset_path,
                    "message": f"Adopted Dataset {dataset_name} is missing at {dataset_path}",
                }
            )
            continue

        expected_owner = dataset.get("owner")
        actual_owner = actual_dataset.get("owner")
        if expected_owner and actual_owner != expected_owner:
            expected_uid = expected_owner.get("uid")
            expected_gid = expected_owner.get("gid")
            actual_uid = actual_owner.get("uid") if actual_owner else None
            actual_gid = actual_owner.get("gid") if actual_owner else None
            dataset_findings.append(
                {
                    "code": "dataset_owner_drift",
                    "dataset": dataset_name,
                    "path": dataset_path,
                    "expected": expected_owner,
                    "actual": actual_owner,
                    "message": (
                        f"Adopted Dataset {dataset_name} root owner is {actual_uid}:{actual_gid}, "
                        f"expected {expected_uid}:{expected_gid}"
                    ),
                }
            )

    desired_nfs_shares = derive_desired_nfs_shares(
        inventory,
        include_ephemeral_datasets=acceptance_ephemeral_datasets and not destroy_ephemeral_datasets,
    )
    share_findings = _share_findings(desired_nfs_shares, reality.nfs_shares)
    if acceptance_ephemeral_datasets and destroy_ephemeral_datasets:
        share_findings.extend(_ephemeral_cleanup_share_findings(inventory, reality.nfs_shares))
    preflight_findings = _mount_preflight_findings(inventory, reality.previous_mounts)
    blocking_codes = {"unmanaged_share_overlap"}

    blocked = bool(dataset_findings) or any(
        finding["code"] in blocking_codes for finding in share_findings
    )
    confirmation_required = bool(preflight_findings) and not confirm_disruptive_mount_changes
    blocked = blocked or confirmation_required
    write_actions = []
    if apply and not blocked:
        share_write_actions = _write_actions(desired_nfs_shares, reality.nfs_shares)
        if destroy_ephemeral_datasets:
            write_actions = share_write_actions + dataset_write_actions
        else:
            write_actions = dataset_write_actions + share_write_actions
        if client:
            _apply_write_actions(client, write_actions)

    result = {
        "read_only": not apply,
        "blocked": blocked,
        "write_actions": write_actions,
        "rollback_actions": [],
        "connection": _redacted_connection(inventory),
        "dataset_findings": dataset_findings,
        "desired_nfs_shares": desired_nfs_shares,
        "preflight_findings": preflight_findings,
        "confirmation_required": confirmation_required,
        "share_findings": share_findings,
    }
    if client:
        result["api_operations"] = client.operations
    return result


def _ephemeral_dataset_write_actions_and_findings(dataset, reality, destroy=False):
    dataset_path = dataset.get("path")
    if not dataset_path:
        return [], []
    actual_dataset = reality.datasets.get(dataset_path)
    if destroy:
        if _is_fortress_ephemeral_dataset(dataset, actual_dataset):
            return [
                {
                    "action": "delete_dataset",
                    "dataset": dataset.get("name"),
                    "path": dataset_path,
                }
            ], []
        if actual_dataset:
            dataset_name = dataset.get("name")
            return [], [
                {
                    "code": "unmarked_ephemeral_dataset",
                    "dataset": dataset_name,
                    "path": dataset_path,
                    "message": (
                        f"Ephemeral Dataset {dataset_name} at {dataset_path} is not marked "
                        "as fortress-created; leaving it behind"
                    ),
                }
            ]
        return [], []
    if actual_dataset:
        return [], []
    return [{"action": "create_dataset", "dataset": _ephemeral_dataset_payload(dataset)}], []


def _ephemeral_dataset_payload(dataset):
    return {
        "name": dataset["name"],
        "path": dataset["path"],
        "lifecycle": "ephemeral",
        "fortress_marker": _ephemeral_dataset_marker(dataset["name"]),
    }


def _ephemeral_dataset_marker(name):
    return f"fortress:ephemeral-dataset:{name}"


def _is_fortress_ephemeral_dataset(dataset, actual_dataset):
    if not actual_dataset:
        return False
    return actual_dataset.get("fortress_marker") == _ephemeral_dataset_marker(dataset.get("name"))


def _write_actions(desired_nfs_shares, existing_nfs_shares):
    existing_by_name = {share.get("name"): share for share in existing_nfs_shares}
    desired_names = {share["name"] for share in desired_nfs_shares}
    actions = []
    for desired in desired_nfs_shares:
        if desired["name"] not in existing_by_name:
            actions.append({"action": "create_nfs_share", "share": _owned_share_payload(desired)})
            continue
        existing = existing_by_name[desired["name"]]
        desired_payload = _owned_share_payload(desired)
        if _is_fortress_owned_share(existing) and _share_drifted(existing, desired_payload):
            actions.append(
                {
                    "action": "update_nfs_share",
                    "share": desired["name"],
                    "desired": desired_payload,
                }
            )
    for existing in sorted(existing_nfs_shares, key=lambda item: item.get("name", "")):
        if _is_fortress_owned_share(existing) and existing.get("name") not in desired_names:
            actions.append(
                {
                    "action": "delete_nfs_share",
                    "share": existing.get("name"),
                    "path": existing.get("path"),
                }
            )
    return actions


def _apply_write_actions(client, write_actions):
    for action in write_actions:
        if action["action"] == "create_dataset":
            client.create_dataset(action["dataset"])
        elif action["action"] == "delete_dataset":
            client.delete_dataset(action["dataset"], action["path"])
        elif action["action"] == "create_nfs_share":
            client.create_nfs_share(action["share"])
        elif action["action"] == "update_nfs_share":
            client.update_nfs_share(action["share"], action["desired"])
        elif action["action"] == "delete_nfs_share":
            client.delete_nfs_share(action["share"])


def _owned_share_payload(desired):
    return {
        "name": desired["name"],
        "path": desired["path"],
        "protocol": desired["protocol"],
        "access": desired["access"],
        "clients": desired["clients"],
        "fortress_owned": True,
        "fortress_marker": _fortress_marker(desired["name"]),
    }


def _fortress_marker(name):
    return f"fortress:nfs-share:{name}"


def _share_drifted(existing, desired):
    for key in ("path", "access", "clients", "fortress_marker"):
        if existing.get(key) != desired.get(key):
            return True
    return False


def _mount_preflight_findings(inventory, previous_mounts):
    previous_by_key = {
        (mount.get("vm"), mount.get("name")): mount
        for mount in previous_mounts
        if mount.get("vm") and mount.get("name")
    }
    current_by_key = {}
    for vm_name, vm in inventory.vms.items():
        for mount in vm.get("mounts", []) or []:
            if mount.get("name"):
                current_by_key[(vm_name, mount["name"])] = mount

    findings = []
    for vm_name, mount_name in sorted(previous_by_key):
        previous = previous_by_key[(vm_name, mount_name)]
        current = current_by_key.get((vm_name, mount_name))
        if not current:
            findings.append(
                {
                    "code": "mount_removed",
                    "vm": vm_name,
                    "mount": mount_name,
                    "dataset": previous.get("dataset"),
                    "message": f"Mount {mount_name} on VM {vm_name} was removed",
                }
            )
            continue
        if previous.get("access") != current.get("access"):
            findings.append(
                {
                    "code": "mount_access_changed",
                    "vm": vm_name,
                    "mount": mount_name,
                    "previous": previous.get("access"),
                    "current": current.get("access"),
                    "message": (
                        f"Mount {mount_name} on VM {vm_name} access changed from "
                        f"{previous.get('access')} to {current.get('access')}"
                    ),
                }
            )
        if previous.get("mount_point") != current.get("mount_point"):
            findings.append(
                {
                    "code": "mount_point_changed",
                    "vm": vm_name,
                    "mount": mount_name,
                    "previous": previous.get("mount_point"),
                    "current": current.get("mount_point"),
                    "message": (
                        f"Mount {mount_name} on VM {vm_name} mount_point changed from "
                        f"{previous.get('mount_point')} to {current.get('mount_point')}"
                    ),
                }
            )
    return findings


def derive_desired_nfs_shares(inventory, include_ephemeral_datasets=False):
    datasets_by_name = {
        dataset.get("name"): dataset
        for dataset in inventory.datasets.values()
        if dataset.get("name")
        and (include_ephemeral_datasets or dataset.get("lifecycle", "adopted") == "adopted")
    }
    grouped = {}
    for vm in inventory.vms.values():
        clients = _vm_static_addresses(vm)
        for mount in vm.get("mounts", []) or []:
            if mount.get("protocol") != "nfs":
                continue
            dataset_name = mount.get("dataset")
            dataset = datasets_by_name.get(dataset_name)
            if not dataset:
                continue
            key = (dataset_name, dataset.get("path"), mount.get("protocol"), mount.get("access"))
            grouped.setdefault(key, set()).update(clients)

    desired = []
    for (dataset_name, path, protocol, access), clients in sorted(grouped.items()):
        desired.append(
            {
                "name": f"fortress-{protocol}-{dataset_name}-{access.replace('_', '-')}",
                "dataset": dataset_name,
                "path": path,
                "protocol": protocol,
                "access": access,
                "clients": sorted(clients),
            }
        )
    return desired


def _share_findings(desired_nfs_shares, existing_nfs_shares):
    existing_by_name = {share.get("name"): share for share in existing_nfs_shares}
    desired_names = {share["name"] for share in desired_nfs_shares}
    findings = []
    for desired in desired_nfs_shares:
        if desired["name"] not in existing_by_name:
            findings.append(
                {
                    "code": "missing_share",
                    "share": desired["name"],
                    "dataset": desired["dataset"],
                    "path": desired["path"],
                    "message": f"Desired NFS Share {desired['name']} is missing",
                }
            )
    for share in sorted(existing_nfs_shares, key=lambda item: item.get("name", "")):
        if share.get("fortress_owned") is True and share.get("name") not in desired_names:
            findings.append(
                {
                    "code": "stale_fortress_owned_share",
                    "share": share.get("name"),
                    "path": share.get("path"),
                    "message": f"Fortress-owned NFS Share {share.get('name')} is no longer desired",
                }
            )
    for share in sorted(existing_nfs_shares, key=lambda item: item.get("name", "")):
        if _is_fortress_owned_share(share):
            continue
        for desired in desired_nfs_shares:
            if _paths_overlap(share.get("path"), desired["path"]):
                findings.append(
                    {
                        "code": "unmanaged_share_overlap",
                        "share": share.get("name"),
                        "dataset": desired["dataset"],
                        "path": share.get("path"),
                        "message": (
                            f"Unmanaged NFS Share {share.get('name')} overlaps desired Dataset "
                            f"{desired['dataset']}"
                        ),
                    }
                )
    return findings


def _ephemeral_cleanup_share_findings(inventory, existing_nfs_shares):
    ephemeral_datasets = [
        dataset
        for dataset in inventory.datasets.values()
        if dataset.get("lifecycle") == "ephemeral" and dataset.get("path")
    ]
    findings = []
    for share in sorted(existing_nfs_shares, key=lambda item: item.get("name", "")):
        if _is_fortress_owned_share(share):
            continue
        for dataset in ephemeral_datasets:
            if _paths_overlap(share.get("path"), dataset["path"]):
                findings.append(
                    {
                        "code": "unmanaged_share_overlap",
                        "share": share.get("name"),
                        "dataset": dataset.get("name"),
                        "path": share.get("path"),
                        "message": (
                            f"Unmanaged NFS Share {share.get('name')} overlaps Ephemeral Dataset "
                            f"{dataset.get('name')}"
                        ),
                    }
                )
    return findings


def _is_fortress_owned_share(share):
    return share.get("fortress_owned") is True or share.get("fortress_marker") == _fortress_marker(
        share.get("name")
    )


def _paths_overlap(existing_path, desired_path):
    if not existing_path or not desired_path:
        return False
    return existing_path == desired_path or existing_path.startswith(f"{desired_path}/")


def _vm_static_addresses(vm):
    addresses = []
    for interface in vm.get("network", {}).get("interfaces", []) or []:
        address = interface.get("address")
        if address:
            addresses.append(address.split("/", 1)[0])
    return addresses


def _redacted_connection(inventory):
    endpoints = inventory.globals.get("nas", {}).get("endpoints", {}) or {}
    redacted = {}
    for name, endpoint in sorted(endpoints.items()):
        visible = {}
        has_secret = False
        for key, value in endpoint.items():
            if key.endswith("_env"):
                visible[key] = value
            elif "token" in key or "secret" in key or "password" in key:
                has_secret = True
            else:
                visible[key] = value
        if has_secret:
            visible["credentials"] = "redacted"
        redacted[name] = visible
    return redacted
