"""Rate limiting keyed on the visitor's real IP address.

DRF's throttles identify anonymous visitors by the raw X-Forwarded-For header, which the
client controls: sending a different made-up value with every request gets a fresh limit
every time. Render appends the address that connected to it to that header but keeps
whatever the client sent, so only the right-hand end can be trusted. When that address is
one of Cloudflare's, Cloudflare's own CF-Connecting-IP header names the visitor.
"""

import ipaddress

from rest_framework import throttling

# https://www.cloudflare.com/ips/ (fetched 2026-10-15)
CLOUDFLARE_NETWORKS = [
    ipaddress.ip_network(cidr)
    for cidr in (
        "173.245.48.0/20",
        "103.21.244.0/22",
        "103.22.200.0/22",
        "103.31.4.0/22",
        "141.101.64.0/18",
        "108.162.192.0/18",
        "190.93.240.0/20",
        "188.114.96.0/20",
        "197.234.240.0/22",
        "198.41.128.0/17",
        "162.158.0.0/15",
        "104.16.0.0/13",
        "104.24.0.0/14",
        "172.64.0.0/13",
        "131.0.72.0/22",
        "2400:cb00::/32",
        "2606:4700::/32",
        "2803:f800::/32",
        "2405:b500::/32",
        "2405:8100::/32",
        "2a06:98c0::/29",
        "2c0f:f248::/32",
    )
]


def _parse_ip(value):
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def _is_cloudflare(ip) -> bool:
    return any(ip in network for network in CLOUDFLARE_NETWORKS)


def client_ip(request) -> str:
    # Walk X-Forwarded-For from the right, past the hosting provider's internal hops, to the
    # address that actually connected. Anything further left was written by the client.
    peer = None
    for part in reversed(request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")):
        ip = _parse_ip(part)
        if ip is None:
            break
        peer = ip
        if not ip.is_private:
            break
    if peer is None:
        peer = _parse_ip(request.META.get("REMOTE_ADDR", ""))
    if peer is None:
        return ""

    if _is_cloudflare(peer):
        visitor = _parse_ip(request.META.get("HTTP_CF_CONNECTING_IP", ""))
        if visitor is not None:
            return str(visitor)
    return str(peer)


class ClientIPMixin:
    def get_ident(self, request):
        return client_ip(request)


class ScopedRateThrottle(ClientIPMixin, throttling.ScopedRateThrottle):
    pass


class AnonRateThrottle(ClientIPMixin, throttling.AnonRateThrottle):
    pass


class UserRateThrottle(ClientIPMixin, throttling.UserRateThrottle):
    pass


class ThrottlePostsMixin:
    """For views where reading is unlimited but posting (reviews, bookings) gets a tighter scope."""

    post_throttle_scope = "create"

    def get_throttles(self):
        if self.request.method == "POST":
            self.throttle_scope = self.post_throttle_scope
        return super().get_throttles()
