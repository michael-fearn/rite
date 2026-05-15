import ipaddress
import json
import os
import shlex
import subprocess
import sys
import time

from fortress_inventory.simple_yaml import load_yaml


class AcceptanceTestLifecycle:
    def __init__(self, policy_name, artifact_label, purpose, roles=("primary", "peer"), bridge_error_label=None):
        self.policy_name = policy_name
        self.artifact_label = artifact_label
        self.purpose = purpose
        self.roles = roles
        self.bridge_error_label = bridge_error_label or artifact_label

    def resolve_intent(self, repo_root, inventory, args):
        host_name = args["host"]
        template_name = args["template"]
        endpoint_name = args["endpoint"]
        host = inventory.hosts.get(host_name)
        if not host:
            print(f"Host {host_name!r} is not declared at {repo_root / 'inventory' / 'hosts' / f'{host_name}.yaml'}", file=sys.stderr)
            return 1
        if template_name not in inventory.templates:
            print(f"Template {template_name!r} is not declared at {repo_root / 'inventory' / 'templates' / f'{template_name}.yaml'}", file=sys.stderr)
            return 1
        if template_name not in (host.get("proxmox", {}).get("templates", []) or []):
            print(f"Host {host_name} does not declare Template {template_name} under proxmox.templates", file=sys.stderr)
            return 1
        if endpoint_name not in inventory.nas_endpoints:
            print(f"NAS Endpoint {endpoint_name!r} is not declared at {repo_root / 'inventory' / 'nas' / f'{endpoint_name}.yaml'}", file=sys.stderr)
            return 1
        endpoint = inventory.nas_endpoints[endpoint_name]
        policy = inventory.acceptance_policies.get(self.policy_name)
        if not policy:
            print(f"Acceptance Policy {self.policy_name!r} is not declared at {repo_root / 'inventory' / 'acceptance' / f'{self.policy_name}.yaml'}", file=sys.stderr)
            return 1
        dataset = self.acceptance_dataset(policy, endpoint_name)
        if host_name not in (policy.get("storage_by_host", {}) or {}):
            print(f"Acceptance Policy {self.policy_name} has no storage_by_host entry for Host {host_name}", file=sys.stderr)
            return 1

        vms = []
        for role in self.roles:
            declaration = (policy.get("vms", {}) or {}).get(role, {})
            address = (declaration.get("address_by_host", {}) or {}).get(host_name)
            if not address:
                print(f"Acceptance Policy {self.policy_name} has no {role} address_by_host entry for Host {host_name}", file=sys.stderr)
                return 1
            role_bridge = self.derive_bridge(host_name, host, policy, role)
            if isinstance(role_bridge, int):
                return role_bridge
            vms.append(
                {
                    "role": role,
                    "name": declaration.get("name"),
                    "vmid": declaration.get("vmid"),
                    "address": address,
                    "client": str(ipaddress.ip_interface(address).ip),
                    "bridge": role_bridge,
                }
            )
        return {
            "host": host_name,
            "template": template_name,
            "endpoint": endpoint_name,
            "endpoint_config": endpoint,
            "policy": policy,
            "dataset": dataset,
            "vms": vms,
        }

    def derive_bridge(self, host_name, host, policy, role):
        declaration = (policy.get("vms", {}) or {}).get(role, {})
        address = (declaration.get("address_by_host", {}) or {}).get(host_name)
        if not address:
            return 1
        vm_ip = ipaddress.ip_interface(address).ip
        matches = []
        for bridge in host.get("network", {}).get("bridges", []) or []:
            cidr = bridge.get("cidr")
            if cidr and vm_ip in ipaddress.ip_network(cidr, strict=False):
                matches.append(bridge)
        if len(matches) != 1:
            print(f"{role} VM address {address} must match exactly one Host bridge CIDR; found {len(matches)}", file=sys.stderr)
            return 1
        if not matches[0].get("gateway"):
            print(f"Host {host_name} bridge {matches[0].get('name')} has no gateway for generated {self.bridge_error_label} VM", file=sys.stderr)
            return 1
        return matches[0]

    def refuse_existing_policy_artifacts(self, repo_root):
        policy_path = repo_root / "inventory" / "acceptance" / f"{self.policy_name}.yaml"
        if not policy_path.is_file():
            return 0
        policy = load_yaml(policy_path)
        vms = [
            declaration
            for declaration in (policy.get("vms", {}) or {}).values()
            if declaration.get("name")
        ]
        vm_check = self.refuse_existing_artifacts(repo_root, vms)
        if vm_check != 0:
            return vm_check
        dataset_name = policy.get("dataset")
        if not dataset_name:
            return 0
        path = repo_root / "inventory" / "datasets" / f"{dataset_name}.yaml"
        if path.exists():
            print(f"{path} already exists; refusing to overwrite generated {self.artifact_label} artifact", file=sys.stderr)
            return 1
        return 0

    def refuse_existing_artifacts(self, repo_root, vms):
        for vm in vms:
            for suffix in (".yaml", ".sops.yaml"):
                path = repo_root / "inventory" / "vms" / f"{vm['name']}{suffix}"
                if path.exists():
                    print(f"{path} already exists; refusing to overwrite generated {self.artifact_label} artifact", file=sys.stderr)
                    return 1
        return 0

    def refuse_existing_dataset_artifact(self, repo_root, intent):
        path = self.dataset_artifact_path(repo_root, intent)
        if path.exists():
            print(f"{path} already exists; refusing to overwrite generated {self.artifact_label} artifact", file=sys.stderr)
            return 1
        return 0

    def write_generated_dataset(self, repo_root, intent):
        dataset = intent["dataset"]
        self.dataset_artifact_path(repo_root, intent).write_text(
            f"# Generated {self.artifact_label} Dataset. Do not edit by hand.\n"
            f"name: {dataset['name']}\n"
            f"nas: {dataset['nas']}\n"
            f"path: {dataset['path']}\n"
            "lifecycle: ephemeral\n"
        )

    def acceptance_dataset(self, policy, endpoint_name):
        dataset_name = policy.get("dataset")
        mount = policy.get("mount", {}) or {}
        return {
            "name": dataset_name,
            "nas": endpoint_name,
            "path": f"/mnt/tank/fortress-acceptance/{mount.get('name')}",
            "lifecycle": "ephemeral",
        }

    def dataset_artifact_path(self, repo_root, intent):
        return repo_root / "inventory" / "datasets" / f"{intent['dataset']['name']}.yaml"

    def write_generated_vms(self, repo_root, intent):
        for vm in intent["vms"]:
            self.write_vm_yaml(repo_root / "inventory" / "vms" / f"{vm['name']}.yaml", intent, vm)

    def write_vm_yaml(self, path, intent, vm):
        policy = intent["policy"]
        hardware = policy["hardware"]
        mount = policy["mount"]
        storage = policy["storage_by_host"][intent["host"]]
        path.write_text(
            f"vmid: {vm['vmid']}\n"
            f"description: Generated {self.artifact_label} VM. Do not edit by hand.\n"
            "lifecycle:\n"
            "  kind: operational\n"
            f"  purpose: {self.purpose}\n"
            "  generated: true\n"
            "placement:\n"
            f"  host: {intent['host']}\n"
            "source:\n"
            f"  template: {intent['template']}\n"
            "hardware:\n"
            f"  cores: {hardware['cores']}\n"
            f"  memory: {hardware['memory']}\n"
            "  disks:\n"
            f"    - storage: {storage}\n"
            f"      size: {hardware['disk_size']}\n"
            "network:\n"
            "  interfaces:\n"
            f"    - bridge: {vm['bridge']['name']}\n"
            f"      address: {vm['address']}\n"
            f"      gateway: {vm['bridge']['gateway']}\n"
            "cloud_init:\n"
            f"  hostname: {vm['name']}\n"
            "mounts:\n"
            f"  - name: {mount['name']}\n"
            f"    dataset: {intent['dataset']['name']}\n"
            "    protocol: nfs\n"
            f"    mount_point: {mount['mount_point']}\n"
            f"    access: {mount['access']}\n"
            "backup:\n"
            "  enabled: false\n"
        )

    def run_reconcile(self, repo_root, intent, destroy):
        command = [
            str(repo_root / "scripts" / "nas-reconcile-plan"),
            "--live",
            intent["endpoint"],
            "--acceptance-ephemeral-datasets",
        ]
        if destroy:
            command.append("--destroy-ephemeral-datasets")
        command.append("--apply")
        return run(command)

    def assert_reconcile_share(self, stdout, intent):
        try:
            payload = json.loads(stdout or "{}")
        except json.JSONDecodeError as error:
            return subprocess.CompletedProcess([], 1, "", f"reconcile output was not JSON: {error}")
        expected_clients = sorted(vm["client"] for vm in intent["vms"])
        expected_name = self.share_name(intent)
        matches = [
            share for share in payload.get("desired_nfs_shares", []) or []
            if share.get("name") == expected_name
            and share.get("dataset") == intent["dataset"]["name"]
            and set(expected_clients) <= set(share.get("clients", []))
        ]
        if len(matches) != 1:
            return subprocess.CompletedProcess(
                [],
                1,
                "",
                f"expected one Derived NFS Share {expected_name} with clients {expected_clients}",
            )
        return None

    def provision_vms(self, repo_root, intent, auto_confirm, provisioned, progress=None):
        for vm in intent["vms"]:
            if progress:
                progress(vm)
            command = [str(repo_root / "scripts" / "vm-up"), vm["name"]]
            provisioned.append(vm["name"])
            if auto_confirm:
                command.append("--auto-confirm")
                up = run(command)
            else:
                up = run(command, input_text=f"apply {vm['name']}\n")
            if up.returncode != 0:
                return vm, up
        return None, subprocess.CompletedProcess([], 0, "", "")

    def mount_health_checks(self, intent):
        mount_point = intent["policy"]["mount"]["mount_point"]
        unit = systemd_mount_unit(mount_point)
        checks = []
        for vm in intent["vms"]:
            checks.append(ssh_check(vm, ["systemctl", "is-active", unit]))
            checks.append(ssh_check(vm, ["findmnt", mount_point]))
        return checks

    def verify_checks(self, repo_root, checks):
        hostvars = load_hostvars(repo_root)
        for check in checks:
            result = verify_ssh_check(repo_root, check["vm"]["name"], hostvars, check["command"], check.get("expected_stdout"))
            if result.returncode != 0:
                return result
        return subprocess.CompletedProcess([], 0, "", "")

    def verify_named_checks(self, repo_root, checks, progress=None):
        hostvars = load_hostvars(repo_root)
        for check in checks:
            if progress:
                progress(check["description"])
            result = self.verify_check(repo_root, hostvars, check)
            if result.returncode != 0:
                return result
        return subprocess.CompletedProcess([], 0, "", "")

    def load_verification_hostvars(self, repo_root):
        return load_hostvars(repo_root)

    def verify_check(self, repo_root, hostvars, check):
        return verify_ssh_check(repo_root, check["vm"]["name"], hostvars, check["command"], check.get("expected_stdout"))

    def failed_after_generation(self, repo_root, intent, phase, result, keep_on_fail, generated, provisioned, require_nas_cleanup=True):
        message = f"{phase} failed: {phase_detail(result)}"
        if keep_on_fail:
            resource_label = self.artifact_label.replace("Acceptance", "acceptance")
            print(f"{message}; preserved {resource_label} resources for inspection", file=sys.stderr)
            return 1
        if generated:
            cleanup = self.cleanup_resources(repo_root, intent, provisioned, require_nas_cleanup=require_nas_cleanup)
            if cleanup.returncode != 0:
                print(f"{message}; cleanup also failed: {phase_detail(cleanup)}", file=sys.stderr)
                return 1
        print(message, file=sys.stderr)
        return 1

    def cleanup_resources(self, repo_root, intent, provisioned=None, require_nas_cleanup=True):
        provisioned = set(provisioned or [])
        stderr = []
        for vm in intent["vms"]:
            if vm["name"] in provisioned:
                result = run([str(repo_root / "scripts" / "vm-destroy"), vm["name"], "--delete-vm-yaml"])
                if result.returncode != 0:
                    stderr.append(phase_detail(result))
            else:
                self.delete_generated_artifacts(repo_root, vm["name"], stderr)
        reconcile = self.run_reconcile(repo_root, intent, destroy=True)
        if reconcile.returncode != 0:
            stderr.append(phase_detail(reconcile))
        elif require_nas_cleanup:
            assertion = self.assert_cleanup_removes_nas_resources(reconcile.stdout, intent)
            if assertion:
                stderr.append(phase_detail(assertion))
        self.delete_generated_dataset_artifact(repo_root, intent, stderr)
        if stderr:
            return subprocess.CompletedProcess([], 1, "", "; ".join(stderr))
        return subprocess.CompletedProcess([], 0, "", "")

    def assert_cleanup_removes_nas_resources(self, stdout, intent):
        try:
            payload = json.loads(stdout or "{}")
        except json.JSONDecodeError as error:
            return subprocess.CompletedProcess([], 1, "", f"cleanup output was not JSON: {error}")
        expected_dataset = intent["dataset"]["name"]
        expected_share = self.share_name(intent)
        operations = (payload.get("api_operations") or []) + (payload.get("write_actions") or [])
        deleted_dataset = any(
            operation.get("method") == "delete_dataset"
            and operation.get("dataset") == expected_dataset
            for operation in operations
        ) or any(
            operation.get("action") == "delete_dataset"
            and operation.get("dataset") == expected_dataset
            for operation in operations
        )
        deleted_share = any(
            operation.get("method") == "delete_nfs_share"
            and operation.get("share") == expected_share
            for operation in operations
        ) or any(
            operation.get("action") == "delete_nfs_share"
            and operation.get("share") == expected_share
            for operation in operations
        )
        errors = []
        if not deleted_dataset:
            errors.append(f"expected cleanup to delete Ephemeral Dataset {expected_dataset}")
        if not deleted_share:
            errors.append(f"expected cleanup to delete Derived NFS Share {expected_share}")
        postcondition_findings = payload.get("destroy_postcondition_findings")
        if postcondition_findings is None:
            errors.append("cleanup did not verify NAS destroy postconditions")
        else:
            errors.extend(finding.get("message") for finding in postcondition_findings if finding.get("message"))
        if errors:
            return subprocess.CompletedProcess([], 1, "", "; ".join(errors))
        return None

    def delete_generated_artifacts(self, repo_root, vm_name, stderr):
        for suffix in (".sops.yaml", ".yaml"):
            path = repo_root / "inventory" / "vms" / f"{vm_name}{suffix}"
            try:
                path.unlink()
            except FileNotFoundError:
                continue
            except OSError as error:
                stderr.append(f"failed to delete generated artifact {path}: {error}")

    def delete_generated_dataset_artifact(self, repo_root, intent, stderr):
        path = self.dataset_artifact_path(repo_root, intent)
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError as error:
            stderr.append(f"failed to delete generated artifact {path}: {error}")

    def share_name(self, intent):
        return f"fortress-nfs-{intent['dataset']['name']}-{intent['policy']['mount']['access'].replace('_', '-')}"


def ssh_check(vm, remote_command, expected_stdout=None):
    return {"vm": vm, "command": remote_command, "expected_stdout": expected_stdout}


def verify_ssh_check(repo_root, vm_name, hostvars, remote_command, expected_stdout):
    attempts = int(os.environ.get("FORTRESS_VERIFY_RETRIES", "12"))
    delay = float(os.environ.get("FORTRESS_VERIFY_RETRY_DELAY", "5"))
    last_result = subprocess.CompletedProcess(remote_command, 1, "", "")
    for attempt in range(attempts):
        result = ssh_root(repo_root, vm_name, hostvars, remote_command)
        if result.returncode == 0 and (expected_stdout is None or result.stdout.strip() == expected_stdout):
            return result
        if expected_stdout is not None and result.returncode == 0:
            result = subprocess.CompletedProcess(
                remote_command,
                1,
                result.stdout,
                f"expected {expected_stdout!r}, got {result.stdout.strip()!r}",
            )
        last_result = result
        if attempt + 1 < attempts:
            time.sleep(delay)
    return last_result


def systemd_mount_unit(mount_point):
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
        allowed = char.isalnum() or char in ":_."
        if allowed and not (at_start and char == "."):
            escaped.append(char)
        else:
            escaped.extend(f"\\x{byte:02x}" for byte in char.encode())
        at_start = False
    return f"{''.join(escaped)}.mount"


def load_hostvars(repo_root):
    result = subprocess.run(
        ["ansible-inventory", "-i", str(repo_root / "inventory" / "fortress.yaml"), "--list"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return json.loads(result.stdout).get("_meta", {}).get("hostvars", {})


def ssh_root(repo_root, vm_name, hostvars, remote_command):
    vm_vars = hostvars.get(vm_name, {})
    ansible_host = _ansible_value(vm_vars.get("ansible_host"))
    key_file = _ansible_value(vm_vars.get("ansible_ssh_private_key_file"))
    user = _ansible_value(vm_vars.get("ansible_user")) or "admin"
    if not ansible_host or not key_file:
        return subprocess.CompletedProcess(remote_command, 1, "", f"VM {vm_name} missing Ansible SSH connection vars")
    remote_shell_command = f"sudo sh -lc {shlex.quote(shlex.join(remote_command))}"
    return run(
        [
            str(repo_root / "scripts" / "decrypt-keys"),
            f"inventory/vms/{vm_name}.sops.yaml",
            "--",
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-i",
            key_file,
            f"{user}@{ansible_host}",
            remote_shell_command,
        ]
    )


def _ansible_value(value):
    if isinstance(value, dict) and set(value) == {"__ansible_unsafe"}:
        return value["__ansible_unsafe"]
    return value


def run(command, input_text=None, env=None):
    try:
        return subprocess.run(
            command,
            input=input_text,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        return subprocess.CompletedProcess(command, 1, "", str(error))


def phase_detail(result):
    return "\n".join(
        stream.strip()
        for stream in (result.stdout, result.stderr)
        if stream and stream.strip()
    )
