# Caddy remains ingress while Authentik provides optional ingress auth

Caddy remains the internal Ingress responsible for HTTP routing, TLS termination, and generated `*.fearn.cloud` reverse-proxy configuration. Authentik runs on the Identity VM and provides authentication only for Services that explicitly opt into Ingress Auth.

Authentik's proxy provider can proxy or forward-auth applications, but using it as the general ingress would blur identity policy with ordinary routing and make non-Authentik-protected Services depend on the identity stack. Keeping Caddy as the boring routing layer preserves a single generated ingress surface while allowing Authentik to protect selected internal applications.
