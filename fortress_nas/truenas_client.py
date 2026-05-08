from contextlib import contextmanager


MANAGEMENT_API_REACHABILITY = "management API reachability"
NAS_RECONCILE_CREDENTIAL_AUTHENTICATION = "NAS Reconcile Credential authentication"
DATASET_READ = "Dataset read"
NFS_SHARE_READ = "NFS Share read"
NFS_SHARE_WRITE = "NFS Share write"


class TrueNasCapabilityError(Exception):
    def __init__(self, capability, reason):
        self.capability = capability
        self.reason = reason
        super().__init__(f"{capability} failed: {reason}")


class LiveTrueNasClient:
    def __init__(self, client, credential):
        self._client = client
        self._credential = credential

    @classmethod
    @contextmanager
    def connect(cls, management_address, credential, client_class=None, tls_verify=True):
        if client_class is None:
            from truenas_api_client import Client

            client_class = Client

        uri = f"wss://{management_address}/api/current"
        try:
            with client_class(uri=uri, verify_ssl=tls_verify) as client:
                try:
                    _login_with_api_key(client, credential)
                except Exception as error:
                    raise TrueNasCapabilityError(
                        NAS_RECONCILE_CREDENTIAL_AUTHENTICATION,
                        _safe_reason(error, credential),
                    ) from error
                try:
                    if hasattr(client, "ping"):
                        client.ping()
                    else:
                        client.call("core.ping")
                except Exception as error:
                    raise TrueNasCapabilityError(
                        MANAGEMENT_API_REACHABILITY, _safe_reason(error, credential)
                    ) from error
                yield cls(client, credential)
        except TrueNasCapabilityError:
            raise
        except Exception as error:
            raise TrueNasCapabilityError(
                MANAGEMENT_API_REACHABILITY, _safe_reason(error, credential)
            ) from error

    def preflight(self):
        self._call(DATASET_READ, "pool.dataset.query", [], {"limit": 1})
        self._call(NFS_SHARE_READ, "sharing.nfs.query", [], {"limit": 1})
        # TrueNAS does not expose a stable non-mutating NFS Share write permission
        # probe here; live apply relies on the actual reconcile operation to fail safely.

    def datasets(self):
        return self._call(DATASET_READ, "pool.dataset.query")

    def nfs_shares(self):
        return self._call(NFS_SHARE_READ, "sharing.nfs.query")

    def filesystem_stat(self, path):
        return self._call(DATASET_READ, "filesystem.stat", path)

    def create_nfs_share(self, share):
        return self._call(NFS_SHARE_WRITE, "sharing.nfs.create", _nfs_share_payload(share))

    def update_nfs_share(self, share, desired):
        existing = self._find_nfs_share(share)
        return self._call(
            NFS_SHARE_WRITE,
            "sharing.nfs.update",
            existing["id"],
            _nfs_share_payload(desired),
        )

    def delete_nfs_share(self, share):
        existing = self._find_nfs_share(share)
        return self._call(NFS_SHARE_WRITE, "sharing.nfs.delete", existing["id"])

    def _find_nfs_share(self, share_name):
        shares = self._call(NFS_SHARE_READ, "sharing.nfs.query")
        expected_marker = f"fortress:nfs-share:{share_name}"
        for share in shares:
            if share.get("comment") == expected_marker or share.get("comment") == share_name:
                return share
        raise TrueNasCapabilityError(NFS_SHARE_WRITE, f"NFS Share {share_name} was not found")

    def _call(self, capability, method, *args):
        try:
            return self._client.call(method, *args)
        except Exception as error:
            raise TrueNasCapabilityError(capability, _safe_reason(error, self._credential)) from error


def _login_with_api_key(client, credential):
    login_with_api_key = getattr(client, "login_with_api_key", None)
    if callable(login_with_api_key):
        username, separator, key = credential.partition(":")
        if separator:
            login_with_api_key(username, key)
        else:
            login_with_api_key("root", credential)
        return
    _api_key_name, separator, api_key = credential.partition(":")
    if not client.call("auth.login_with_api_key", api_key if separator else credential):
        raise ValueError("Invalid API key")


def _safe_reason(error, credential):
    text = str(error).strip()
    if not text:
        return error.__class__.__name__
    if credential:
        text = text.replace(credential, "[redacted]")
        username, separator, key = credential.partition(":")
        if separator:
            text = text.replace(key, "[redacted]")
    return text


def _nfs_share_payload(share):
    return {
        "paths": [share["path"]],
        "comment": share["fortress_marker"],
        "ro": share.get("access") == "read_only",
        "hosts": share.get("clients", []),
        "enabled": True,
    }
