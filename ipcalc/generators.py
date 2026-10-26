"""Configuration snippets and cloud subnet reservation rules."""

from __future__ import annotations

from dataclasses import dataclass

import ipaddress

from .core import (
    IPv4Address,
    IPv6Address,
    ParsedInput,
    format_count,
    host_info,
    ipv6_slash64,
)


def suggested_host(parsed: ParsedInput) -> str:
    """A sensible first host address for interface examples."""
    if parsed.version == 6:
        if parsed.network.prefixlen >= 128:
            return str(parsed.network.network_address)
        return str(parsed.network.network_address + 1)
    info = host_info(parsed.network)
    if info.first is not None:
        return str(info.first)
    return str(parsed.network.network_address)


def _desc(description: str) -> str:
    description = (description or "").strip()
    return description or "Configured by IP Subnet Calculator"


def cisco_interface(
    parsed: ParsedInput,
    *,
    interface: str = "GigabitEthernet0/1",
    description: str = "",
    host: str | None = None,
) -> str:
    host = host or suggested_host(parsed)
    desc = _desc(description)
    if parsed.version == 4:
        return (
            f"interface {interface}\n"
            f" description {desc}\n"
            f" ip address {host} {parsed.network.netmask}\n"
            " no shutdown\n"
        )
    return (
        f"interface {interface}\n"
        f" description {desc}\n"
        f" ipv6 address {host}/{parsed.prefixlen}\n"
        " ipv6 enable\n"
        " no shutdown\n"
    )


def cisco_acl(parsed: ParsedInput, *, acl_name: str = "IPV4-ALLOW") -> str:
    network = parsed.network
    if network.version == 4:
        if network.prefixlen == 0:
            entry = "access-list 10 permit any"
        elif network.prefixlen == 32:
            entry = f"access-list 10 permit host {network.network_address}"
        else:
            entry = f"access-list 10 permit {network.network_address} {network.hostmask}"
        return (
            "! Standard ACL — place near the destination\n"
            f"{entry}\n"
            "! Extended example with an explicit destination\n"
            f"access-list 100 permit ip {network.network_address} {network.hostmask} any\n"
        )
    return (
        f"ipv6 access-list {acl_name}\n"
        f" permit ipv6 {network} any\n"
        "!\n"
        f"interface GigabitEthernet0/1\n"
        f" ipv6 traffic-filter {acl_name} in\n"
    )


def juniper_interface(
    parsed: ParsedInput,
    *,
    interface: str = "ge-0/0/0",
    unit: int = 0,
    description: str = "",
    host: str | None = None,
) -> str:
    host = host or suggested_host(parsed)
    desc = _desc(description).replace('"', "")
    family = "inet" if parsed.version == 4 else "inet6"
    return (
        f'set interfaces {interface} description "{desc}"\n'
        f"set interfaces {interface} unit {unit} family {family} address "
        f"{host}/{parsed.prefixlen}\n"
    )


def linux_interface(
    parsed: ParsedInput,
    *,
    dev: str = "eth0",
    host: str | None = None,
) -> str:
    host = host or suggested_host(parsed)
    if parsed.version == 4:
        return (
            f"sudo ip addr add {host}/{parsed.prefixlen} dev {dev}\n"
            f"sudo ip link set {dev} up\n"
        )
    return (
        f"sudo ip -6 addr add {host}/{parsed.prefixlen} dev {dev}\n"
        f"sudo ip link set {dev} up\n"
    )


@dataclass(frozen=True)
class CloudRule:
    provider: str
    reserved_head: int
    reserved_tail: int
    reserved_notes: str
    shortest_prefix: int
    longest_prefix: int
    supported_note: str


_CLOUD_V4 = (
    CloudRule(
        provider="AWS",
        reserved_head=4,
        reserved_tail=1,
        reserved_notes="Network, VPC router, DNS, future use, broadcast",
        shortest_prefix=16,
        longest_prefix=28,
        supported_note="VPC subnet IPv4 blocks must be between /16 and /28.",
    ),
    CloudRule(
        provider="Azure",
        reserved_head=4,
        reserved_tail=1,
        reserved_notes="Network, default gateway, two DNS addresses, broadcast",
        shortest_prefix=2,
        longest_prefix=29,
        supported_note="Azure subnets are typically /29 or larger.",
    ),
    CloudRule(
        provider="GCP",
        reserved_head=2,
        reserved_tail=2,
        reserved_notes="Network, default gateway, second-to-last, broadcast",
        shortest_prefix=8,
        longest_prefix=29,
        supported_note="GCP subnet primary ranges are typically /29 or larger.",
    ),
)


def cloud_rows(parsed: ParsedInput) -> list[dict[str, str]]:
    """Reserved-address rules for AWS, Azure, and GCP."""
    network = parsed.network
    rows: list[dict[str, str]] = []
    if network.version == 4:
        total = network.num_addresses
        for rule in _CLOUD_V4:
            reserved_total = rule.reserved_head + rule.reserved_tail
            supported = (
                rule.shortest_prefix <= network.prefixlen <= rule.longest_prefix
                and total > reserved_total
            )
            if not supported:
                rows.append(
                    {
                        "provider": rule.provider,
                        "supported": "No",
                        "reserved": str(reserved_total),
                        "first_usable": "—",
                        "last_usable": "—",
                        "usable": "0",
                        "notes": rule.supported_note,
                    }
                )
                continue
            first = int(network.network_address) + rule.reserved_head
            last = int(network.broadcast_address) - rule.reserved_tail
            usable = max(0, last - first + 1)
            rows.append(
                {
                    "provider": rule.provider,
                    "supported": "Yes",
                    "reserved": f"{reserved_total} ({rule.reserved_notes})",
                    "first_usable": str(IPv4Address(first)),
                    "last_usable": str(IPv4Address(last)),
                    "usable": format_count(usable),
                    "notes": rule.supported_note,
                }
            )
        return rows

    # IPv6 subnets are normally /64 in all three clouds.
    for rule in _CLOUD_V4:
        supported = network.prefixlen == 64
        if not supported:
            rows.append(
                {
                    "provider": rule.provider,
                    "supported": "No",
                    "reserved": "—",
                    "first_usable": "—",
                    "last_usable": "—",
                    "usable": "0",
                    "notes": "Use a /64 for a cloud IPv6 subnet.",
                }
            )
            continue
        first = int(network.network_address) + 1
        last = int(network.broadcast_address)
        rows.append(
            {
                "provider": rule.provider,
                "supported": "Yes",
                "reserved": "1 (network address; IPv6 has no broadcast)",
                "first_usable": str(IPv6Address(first)),
                "last_usable": str(IPv6Address(last)),
                "usable": format_count(last - first + 1),
                "notes": "IPv6 /64 subnet; confirm provider-specific reservations.",
            }
        )
    return rows


def acl_wildcard(parsed: ParsedInput) -> str:
    if parsed.version == 4:
        return str(parsed.network.hostmask)
    return "n/a (IPv6 ACLs use prefixes, not wildcard masks)"


def cisco_acl_entries(parsed: ParsedInput) -> str:
    """One-line ACL entries for quick copy/paste."""
    network = parsed.network
    if network.version == 4:
        return f"permit {network.network_address} {network.hostmask}"
    return f"permit ipv6 {network} any"


def ipv6_nd_note(parsed: ParsedInput) -> str:
    return (
        f"Advertised prefix: {parsed.network} · "
        f"{ipv6_slash64(parsed.prefixlen)[1]}"
    )
