set positional-arguments

# Show the operator command surface.
default:
    @just --list

# Run the full local test and pre-commit suite.
test:
    pre-commit run --all-files

# Bootstrap a physical Host and mint its initial secrets.
host-bootstrap host:
    @./scripts/host-bootstrap {{host}}

# Converge Host configuration; optional tags limits Ansible execution.
host-configure host tags="":
    @./scripts/host-configure {{host}} "{{tags}}"

# Open an SSH shell to a Host.
host-shell host:
    @./scripts/host-shell {{host}}

# Prove a Host is ready by composing Bootstrap, Configure, Template, and Acceptance workflows.
host-up host endpoint="all" auto_confirm="false" keep_on_fail="false":
    @./scripts/host-up {{host}} endpoint={{endpoint}} auto_confirm={{auto_confirm}} keep_on_fail={{keep_on_fail}}

# Apply routine in-place software maintenance to one Host.
host-update host:
    @./scripts/host-update {{host}}

# Provision one VM through prepare, selected-VM Tofu apply, and configure.
vm-up vm auto_confirm="false":
    @if [ "{{auto_confirm}}" = "true" ] || [ "{{auto_confirm}}" = "auto_confirm=true" ]; then ./scripts/vm-up {{vm}} --auto-confirm; else ./scripts/vm-up {{vm}}; fi

# Configure an already-provisioned VM with Ansible.
vm-configure vm:
    @./scripts/vm-configure {{vm}}

# Apply routine in-place software maintenance to one VM.
vm-update vm:
    @./scripts/vm-update {{vm}}

# Open an SSH shell to a VM.
vm-shell vm:
    @./scripts/vm-shell {{vm}}

# Destroy one VM; delete_vm_yaml=true also removes its Inventory file.
vm-destroy vm delete_vm_yaml="false":
    @if [ "{{delete_vm_yaml}}" = "true" ] || [ "{{delete_vm_yaml}}" = "delete_vm_yaml=true" ]; then ./scripts/vm-destroy {{vm}} --delete-vm-yaml; else ./scripts/vm-destroy {{vm}}; fi

# Deploy a Service from Inventory to its target VM.
service-deploy service:
    @./scripts/service-deploy {{service}}

# Launch a Service by converging its Backend VM, deploying it, and refreshing Ingress when declared.
service-launch service auto_confirm="false":
    @if [ "{{auto_confirm}}" = "true" ] || [ "{{auto_confirm}}" = "auto_confirm=true" ]; then ./scripts/service-launch {{service}} --auto-confirm; else ./scripts/service-launch {{service}}; fi

# Launch a Service Group by converging its shared Backend VM, deploying Services in order, and refreshing Ingress once.
service-group-launch group auto_confirm="false":
    @if [ "{{auto_confirm}}" = "true" ] || [ "{{auto_confirm}}" = "auto_confirm=true" ]; then ./scripts/service-group-launch {{group}} --auto-confirm; else ./scripts/service-group-launch {{group}}; fi

# Apply routine in-place runtime maintenance to one Service.
service-update service auto_confirm="false":
    @if [ "{{auto_confirm}}" = "true" ] || [ "{{auto_confirm}}" = "auto_confirm=true" ]; then ./scripts/service-update {{service}} --auto-confirm; else ./scripts/service-update {{service}}; fi

# Apply declared Instrumentation across ordinary VMs and refresh Observability.
instrumentation-converge:
    @./scripts/instrumentation-converge

# Plan NAS Dataset and Share changes against a captured reality JSON file.
nas-reconcile-plan reality_json:
    @./scripts/nas-reconcile-plan --reality-json {{reality_json}}

# Apply NAS Dataset and Share changes against a captured reality JSON file.
nas-reconcile reality_json confirm_disruptive_mount_changes="false":
    @if [ "{{confirm_disruptive_mount_changes}}" = "true" ] || [ "{{confirm_disruptive_mount_changes}}" = "confirm_disruptive_mount_changes=true" ]; then ./scripts/nas-reconcile-plan --reality-json {{reality_json}} --apply --confirm-disruptive-mount-changes; else ./scripts/nas-reconcile-plan --reality-json {{reality_json}} --apply; fi

# Plan live NAS changes against a NAS endpoint such as endpoint=truenas.
nas-reconcile-live-plan endpoint:
    @./scripts/nas-reconcile-plan --live {{endpoint}}

# Apply live NAS changes against a NAS endpoint such as endpoint=truenas.
nas-reconcile-live endpoint confirm_disruptive_mount_changes="false":
    @if [ "{{confirm_disruptive_mount_changes}}" = "true" ] || [ "{{confirm_disruptive_mount_changes}}" = "confirm_disruptive_mount_changes=true" ]; then ./scripts/nas-reconcile-plan --live {{endpoint}} --apply --confirm-disruptive-mount-changes; else ./scripts/nas-reconcile-plan --live {{endpoint}} --apply; fi

# Build all Templates declared for a Host.
templates-build host:
    @./scripts/templates-build {{host}}

# Verify a Template on a Host; keep_on_fail=true preserves generated artifacts.
template-verify host template keep_on_fail="false":
    @./scripts/template-verify host={{host}} template={{template}} keep_on_fail={{keep_on_fail}}

# Apply routine reusable base software maintenance to one Template on one Host.
template-update host template keep_on_fail="false":
    @./scripts/template-update host={{host}} template={{template}} keep_on_fail={{keep_on_fail}}

# Apply routine reusable base software maintenance to one Template on every declaring Host.
template-update-all template keep_on_fail="false":
    @./scripts/template-update host=all template={{template}} keep_on_fail={{keep_on_fail}}

# Run NFS shared-mount acceptance against a NAS endpoint such as endpoint=truenas.
acceptance-nfs-shared-mount host template endpoint auto_confirm="false" keep_on_fail="false":
    @host="{{host}}"; template="{{template}}"; endpoint="{{endpoint}}"; auto_confirm="{{auto_confirm}}"; keep_on_fail="{{keep_on_fail}}"; ./scripts/acceptance-nfs-shared-mount host="${host#host=}" template="${template#template=}" endpoint="${endpoint#endpoint=}" auto_confirm="${auto_confirm#auto_confirm=}" keep_on_fail="${keep_on_fail#keep_on_fail=}"

# Run service-layer acceptance against a NAS endpoint such as endpoint=truenas.
acceptance-service-layer host template endpoint auto_confirm="false" keep_on_fail="false":
    @host="{{host}}"; template="{{template}}"; endpoint="{{endpoint}}"; auto_confirm="{{auto_confirm}}"; keep_on_fail="{{keep_on_fail}}"; ./scripts/acceptance-service-layer host="${host#host=}" template="${template#template=}" endpoint="${endpoint#endpoint=}" auto_confirm="${auto_confirm#auto_confirm=}" keep_on_fail="${keep_on_fail#keep_on_fail=}"

# Prove the primary DNS VM and Pi-hole + Unbound Service against live LAN DNS.
acceptance-dns-primary provision="false" auto_confirm="false" external="example.com" internal="":
    @provision="{{provision}}"; auto_confirm="{{auto_confirm}}"; external="{{external}}"; internal="{{internal}}"; ./scripts/acceptance-dns-primary provision="${provision#provision=}" auto_confirm="${auto_confirm#auto_confirm=}" external="${external#external=}" internal="${internal#internal=}"

# Remove generated artifacts for an acceptance workflow.
acceptance-clean-generated-artifacts workflow auto_confirm="false":
    @workflow="{{workflow}}"; auto_confirm="{{auto_confirm}}"; ./scripts/acceptance-clean-generated-artifacts workflow=${workflow#workflow=} auto_confirm=${auto_confirm#auto_confirm=}

# Destroy a Template on a Host; delete_template_yaml=true removes its Inventory file.
template-destroy host template delete_template_yaml="false":
    @if [ "{{delete_template_yaml}}" = "true" ] || [ "{{delete_template_yaml}}" = "delete_template_yaml=true" ]; then ./scripts/template-destroy {{host}} {{template}} --delete-template-yaml; else ./scripts/template-destroy {{host}} {{template}}; fi

# Generate the Caddy ingress config from Inventory.
ingress-regenerate:
    @./scripts/ingress-regenerate
