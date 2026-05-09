import json
import os
import sys
from pathlib import Path

from fortress_nas.truenas_client import LiveTrueNasClient, TrueNasCapabilityError


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) not in (3, 4):
        print(
            "usage: python3 -m fortress_nas.truenas_reality "
            "<endpoint> <management-address> <api-token-env> [tls-verify]",
            file=sys.stderr,
        )
        return 2

    endpoint_name, management_address, api_token_env = argv[:3]
    tls_verify = len(argv) == 3 or argv[3] != "false"
    credential = os.environ.get(api_token_env)
    if not credential:
        print(f"{api_token_env} is not set for NAS Endpoint {endpoint_name}", file=sys.stderr)
        return 1

    fake_reality = os.environ.get("FORTRESS_FAKE_TRUENAS_REALITY_JSON")
    if fake_reality:
        fake_preflight_failure = os.environ.get("FORTRESS_FAKE_TRUENAS_PREFLIGHT_FAILURE")
        if fake_preflight_failure:
            print(fake_preflight_failure, file=sys.stderr)
            return 1
        _write_fake_env_log(api_token_env, credential)
        sys.stdout.write(Path(fake_reality).read_text())
        return 0

    try:
        reality = load_live_truenas_reality(management_address, credential, tls_verify=tls_verify)
    except TrueNasCapabilityError as error:
        print(
            f"TrueNAS preflight failed for NAS Endpoint {endpoint_name}: {error}",
            file=sys.stderr,
        )
        return 1
    except Exception as error:
        print(f"failed to query TrueNAS reality for NAS Endpoint {endpoint_name}: {error}", file=sys.stderr)
        return 1

    json.dump(reality, sys.stdout)
    sys.stdout.write("\n")
    return 0


def load_live_truenas_reality(
    management_address, credential, client_factory=LiveTrueNasClient, tls_verify=True
):
    with client_factory.connect(management_address, credential, tls_verify=tls_verify) as client:
        client.preflight()
        datasets = [_dataset_payload(client, dataset) for dataset in client.datasets()]
        nfs_shares = [_nfs_share_payload(share) for share in client.nfs_shares()]
    return {"datasets": datasets, "nfs_shares": nfs_shares, "previous_mounts": []}


def _dataset_payload(client, dataset):
    mountpoint = _property_value(dataset.get("mountpoint"))
    payload = {"path": mountpoint or f"/mnt/{dataset.get('id')}"}
    comments = _dataset_comments(dataset)
    if isinstance(comments, str) and comments.startswith("fortress:ephemeral-dataset:"):
        payload["fortress_marker"] = comments
    if payload["path"]:
        try:
            stat = client.filesystem_stat(payload["path"])
        except Exception:
            stat = {}
        if "uid" in stat or "gid" in stat:
            payload["owner"] = {"uid": stat.get("uid"), "gid": stat.get("gid")}
    return payload


def _dataset_comments(dataset):
    comments = _property_value(dataset.get("comments"))
    if comments is not None:
        return comments
    user_properties = dataset.get("user_properties") or {}
    return _property_value(user_properties.get("comments"))


def _nfs_share_payload(share):
    paths = share.get("paths") or []
    path = paths[0] if paths else share.get("path")
    comment = share.get("comment")
    name = comment or f"truenas-nfs-{share.get('id')}"
    marker = None
    if isinstance(comment, str) and comment.startswith("fortress:nfs-share:"):
        marker = comment
        name = comment.removeprefix("fortress:nfs-share:")
    payload = {
        "name": name,
        "path": path,
        "access": "read_only" if share.get("ro") else "read_write",
        "clients": share.get("hosts") or share.get("networks") or [],
    }
    for key in ("maproot_user", "maproot_group", "mapall_user", "mapall_group"):
        if share.get(key):
            payload[key] = share[key]
    if marker:
        payload["fortress_marker"] = marker
    return payload


def _property_value(value):
    if isinstance(value, dict):
        return value.get("value") or value.get("rawvalue") or value.get("parsed")
    return value


def _write_fake_env_log(api_token_env, credential):
    log_path = os.environ.get("FORTRESS_FAKE_TRUENAS_ENV_LOG")
    if log_path:
        Path(log_path).write_text(f"{api_token_env}={credential}\n")


if __name__ == "__main__":
    raise SystemExit(main())
