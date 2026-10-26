"""Reverse DNS helpers: PTR names, zones, and RFC 2317 delegation."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

from .core import (
    IPAddress,
    IPNetwork,
    InputError,
    IPv4Address,
    IPv4Network,
    IPv6Network,
)


def reverse_pointer(addr: IPAddress) -> str:
    """Return the full in-addr.arpa or ip6.arpa pointer name."""
    if addr.version == 4:
        return ".".join(reversed(str(addr).split("."))) + ".in-addr.arpa"
    nibbles = addr.exploded.replace(":", "")
    return ".".join(reversed(nibbles)) + ".ip6.arpa"


def _v4_zone_name(network: IPv4Network, octets: int) -> str:
    parts = str(network.network_address).split(".")[:octets]
    return ".".join(reversed(parts)) + ".in-addr.arpa" if parts else "in-addr.arpa"


def _v6_zone_name(network: IPv6Network, nibbles: int) -> str:
    nibble_string = network.network_address.exploded.replace(":", "")
    prefix = nibble_string[:nibbles]
    return ".".join(reversed(prefix)) + ".ip6.arpa" if prefix else "ip6.arpa"


@dataclass(frozen=True)
class ZoneInfo:
    zone: str
    aligned: bool
    version: int
    warning: str | None = None
    rfc2317: bool = False
    parent_zone: str | None = None
    enclosing_prefix: int | None = None


def zone_for_network(network: IPNetwork) -> ZoneInfo:
    """Return the reverse zone that contains ``network``.

    IPv4 delegations traditionally happen on octet boundaries; IPv6
    delegations happen on nibble boundaries.  A non-aligned v4 network in the
    /25–/31 range is a candidate for RFC 2317 classless delegation.
    """
    prefix = network.prefixlen
    if network.version == 4:
        if prefix == 32:
            return ZoneInfo(
                zone=reverse_pointer(network.network_address),
                aligned=True,
                version=4,
                warning="A /32 is a single host; there is no zone to delegate.",
            )
        if prefix % 8 == 0:
            return ZoneInfo(zone=_v4_zone_name(network, prefix // 8), aligned=True, version=4)
        if 24 < prefix < 32:
            parent_zone = _v4_zone_name(network, 3)
            first = int(network.network_address) & 0xFF
            child = f"{first}/{prefix}.{parent_zone}"
            return ZoneInfo(
                zone=child,
                aligned=False,
                version=4,
                warning=(
                    "This prefix is not on an octet boundary. Use RFC 2317 "
                    "classless delegation in the parent /24 zone."
                ),
                rfc2317=True,
                parent_zone=parent_zone,
            )
        enclosing = (prefix // 8) * 8
        return ZoneInfo(
            zone=_v4_zone_name(network, enclosing // 8),
            aligned=False,
            version=4,
            warning=(
                f"Reverse delegation is octet-aligned. The enclosing "
                f"/{enclosing} zone is {_v4_zone_name(network, enclosing // 8)}; "
                "delegations below /25 normally use RFC 2317."
            ),
            enclosing_prefix=enclosing,
        )

    if prefix == 128:
        return ZoneInfo(
            zone=reverse_pointer(network.network_address),
            aligned=True,
            version=6,
            warning="A /128 is a single host; there is no zone to delegate.",
        )
    if prefix % 4 == 0:
        return ZoneInfo(zone=_v6_zone_name(network, prefix // 4), aligned=True, version=6)
    enclosing = (prefix // 4) * 4
    return ZoneInfo(
        zone=_v6_zone_name(network, enclosing // 4),
        aligned=False,
        version=6,
        warning=(
            f"IPv6 reverse delegation is nibble-aligned. The enclosing "
            f"/{enclosing} zone is {_v6_zone_name(network, enclosing // 4)}."
        ),
        enclosing_prefix=enclosing,
    )


def _host_label(addr: IPAddress) -> str:
    if addr.version == 4:
        return "host-" + str(addr).replace(".", "-")
    return "host-" + addr.exploded.replace(":", "-")


def ptr_lines(
    network: IPNetwork, domain: str = "example.com", *, limit: int = 256
) -> tuple[list[str], bool]:
    """Return PTR record lines and whether the list was truncated."""
    domain = domain.strip().strip(".") or "example.com"
    lines: list[str] = []
    truncated = False
    for index, addr in enumerate(network):
        if index >= limit:
            truncated = True
            break
        lines.append(f"{reverse_pointer(addr)} IN PTR {_host_label(addr)}.{domain}.")
    return lines, truncated


def ptr_records(
    network: IPNetwork, domain: str = "example.com", *, limit: int = 256
) -> list[dict[str, str]]:
    lines, _ = ptr_lines(network, domain, limit=limit)
    rows: list[dict[str, str]] = []
    for line in lines:
        owner, _in, _ptr, target = line.split(" ", 3)
        rows.append({"pointer": owner, "target": target})
    return rows


def _soa_lines(zone: str, nameserver: str, domain: str) -> list[str]:
    nameserver = nameserver.strip().strip(".") or "ns1.example.net"
    domain = domain.strip().strip(".") or "example.com"
    return [
        f"$ORIGIN {zone}.",
        "@ 3600 IN SOA "
        f"{nameserver}. hostmaster.{domain}. (",
        "    2026102601 ; serial",
        "    3600       ; refresh",
        "    900        ; retry",
        "    1209600    ; expire",
        "    300 )      ; minimum",
        f"@ 3600 IN NS {nameserver}.",
        "",
    ]


def zone_snippet(
    network: IPNetwork,
    *,
    domain: str = "example.com",
    nameserver: str = "ns1.example.net",
    limit: int = 256,
) -> str:
    info = zone_for_network(network)
    lines = _soa_lines(info.zone, nameserver, domain)
    if info.rfc2317:
        lines.append(
            "; This is the child zone. Add the RFC 2317 delegation records "
            "from the parent zone."
        )
        lines.append("")
    ptrs, truncated = ptr_lines(network, domain, limit=limit)
    lines.extend(ptrs)
    if truncated:
        lines.append(
            f"; ... {network.num_addresses - limit:,} more PTR records omitted "
            "(use $GENERATE in production)."
        )
    return "\n".join(lines) + "\n"


def rfc2317_snippets(
    network: IPNetwork,
    *,
    domain: str = "example.com",
    nameserver: str = "ns1.example.net",
    second_nameserver: str = "ns2.example.net",
) -> tuple[str, str]:
    """Return ``(parent_delegation, child_zone)`` for an RFC 2317 delegation."""
    if network.version != 4:
        raise InputError("RFC 2317 classless delegation applies to IPv4 only.")
    if not 24 < network.prefixlen < 32:
        raise InputError(
            "RFC 2317 is used for IPv4 prefixes between /25 and /31. "
            "Use a larger block for /24 or shorter."
        )
    info = zone_for_network(network)
    if not info.rfc2317 or info.parent_zone is None:
        raise InputError("This network is not a candidate for RFC 2317.")

    first = int(network.network_address) & 0xFF
    size = network.num_addresses
    last = first + size - 1
    child_label = f"{first}/{network.prefixlen}"
    child_zone = f"{child_label}.{info.parent_zone}"
    nameserver = nameserver.strip().strip(".") or "ns1.example.net"
    second_nameserver = second_nameserver.strip().strip(".") or "ns2.example.net"
    domain = domain.strip().strip(".") or "example.com"

    parent_lines = [
        f"; Parent zone: {info.parent_zone}",
        f"$ORIGIN {info.parent_zone}.",
        f"; RFC 2317 delegation for {network}",
        f"{child_label} 3600 IN NS {nameserver}.",
        f"{child_label} 3600 IN NS {second_nameserver}.",
        "; CNAME every owner name in the delegating /24 to the child zone.",
        f"$GENERATE {first}-{last} $ CNAME $.{child_zone}.",
        "",
        "; If your DNS software dislikes '/' in labels, use a hyphen instead:",
        f"; {child_label.replace('/', '-')} 3600 IN NS {nameserver}.",
        f"; $GENERATE {first}-{last} $ CNAME $.{child_label.replace('/', '-')}."
        f"{info.parent_zone}.",
    ]

    child_lines = _soa_lines(child_zone, nameserver, domain)
    child_lines.extend(
        [
            f"; PTR records for {network}",
            f"$GENERATE {first}-{last} $ PTR host-$.{domain}.",
            "",
            "; Expanded example for the first address:",
            f"{first} IN PTR {_host_label(network.network_address)}.{domain}.",
        ]
    )
    return "\n".join(parent_lines) + "\n", "\n".join(child_lines) + "\n"


def zone_hierarchy(network: IPNetwork) -> list[str]:
    """A small explanation of the reverse name for the UI."""
    info = zone_for_network(network)
    lines = [f"Reverse zone: {info.zone}"]
    if info.rfc2317:
        lines.append(f"Parent /24 zone: {info.parent_zone}")
    if info.warning:
        lines.append(info.warning)
    return lines


def ptr_for_address(addr: IPAddress) -> str:
    return reverse_pointer(addr)


def address_from_pointer(pointer: str) -> IPAddress:
    """Parse a PTR owner name back into an address (best effort)."""
    pointer = pointer.strip().strip(".").lower()
    if pointer.endswith(".in-addr.arpa"):
        labels = pointer[: -len(".in-addr.arpa")].split(".")
        if len(labels) != 4:
            raise InputError("An in-addr.arpa pointer must have four octet labels.")
        return IPv4Address(".".join(reversed(labels)))
    if pointer.endswith(".ip6.arpa"):
        labels = pointer[: -len(".ip6.arpa")].split(".")
        if len(labels) != 32:
            raise InputError("An ip6.arpa pointer must have 32 nibble labels.")
        nibbles = "".join(reversed(labels))
        grouped = ":".join(nibbles[i : i + 4] for i in range(0, 32, 4))
        return ipaddress.IPv6Address(grouped)
    raise InputError("Pointer must end in .in-addr.arpa or .ip6.arpa.")
