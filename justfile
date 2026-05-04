set positional-arguments

default:
    @just --list

host-bootstrap host:
    @./scripts/host-bootstrap {{host}}

host-configure host tags="":
    @./scripts/host-configure {{host}} "{{tags}}"

vm-up vm:
    @echo "TODO: prepare, apply, and configure VM {{vm}}"

vm-configure vm:
    @./scripts/vm-configure {{vm}}

vm-destroy vm:
    @echo "TODO: destroy VM {{vm}}"

service-deploy service:
    @echo "TODO: deploy Service {{service}}"

templates-build host:
    @./scripts/templates-build {{host}}

ingress-regenerate:
    @echo "TODO: regenerate Ingress configuration"
