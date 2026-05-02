# Per-entity flat YAML as source of truth

Every managed Entity (Host, VM, Service, Template) is a flat YAML file at a predictable path; JSON Schema enforces shape; both Ansible (via the custom inventory plugin) and OpenTofu (via `yamldecode`) consume the same files directly. There is no Jinja-rendering, constructed-inventory, or dynamic-inventory layer above the YAML. Indirection that feels clean on day one becomes a debugging tax on day ninety: flat files are greppable, diff-friendly, and avoid rendering-vs-applied drift. Adding an Entity is adding one file.
