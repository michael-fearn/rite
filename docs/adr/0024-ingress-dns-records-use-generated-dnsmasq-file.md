# Ingress DNS records use a generated dnsmasq file

Ingress Regeneration writes the fortress-owned Ingress DNS Record Set as a generated dnsmasq configuration file on each opted-in Pi-hole-backed DNS Service, using Pi-hole's `/etc/dnsmasq.d` compatibility surface rather than the Pi-hole API or UI-backed local DNS model. This keeps generated records isolated, authoritatively replaceable, diffable, and easy to clean up after Service hostname changes; the trade-off is that Pi-hole v6 compatibility support must be explicitly enabled for fortress-managed DNS Services.
