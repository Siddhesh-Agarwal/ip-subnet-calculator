"""Core parsing, formatting, and classification for the IP subnet calculator.

All address maths uses Python's :mod:`ipaddress` module, so IPv6 is handled as
128-bit integers rather than being squeezed into 32-bit numbers.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Iterable

IPv4Address = ipaddress.IPv4Address
IPv6Address = ipaddress.IPv6Address
IPAddress = IPv4Address | IPv6Address
IPv4Network = ipaddress.IPv4Network
IPv6Network = ipaddress.IPv6Network
IPNetwork = IPv4Network | IPv6Network

MAX_PREFIX = {4: 32, 6: 128}
BITS = {4: 32, 6: 128}


class InputError(ValueError):
    """A human-readable input validation error."""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedInput:
    """The result of parsing one address/prefix expression."""

    raw: str
    address: IPAddress
    network: IPNetwork
    prefixlen: int
    version: int
    had_prefix: bool
    host_bits_set: bool
    style: str
    note: str | None = None

    @property
    def normalized(self) -> str:
        return str(self.network)

    @property
    def netmask(self) -> str | None:
        return str(self.network.netmask) if self.version == 4 else None

    @property
    def wildcard(self) -> str | None:
        return str(self.network.hostmask) if self.version == 4 else None

    @property
    def prefix_label(self) -> str:
        return f"/{self.prefixlen}"


def _contiguous_prefix_from_mask(mask_value: int, bits: int) -> int | None:
    """Return the prefix length for a contiguous netmask value, else None."""
    all_ones = (1 << bits) - 1
    mask_value &= all_ones
    if mask_value == 0:
        return 0
    inverted = (~mask_value) & all_ones
    if inverted & (inverted + 1) == 0:
        return bits - inverted.bit_length()
    return None


def _mask_from_dotted(token: str) -> tuple[int, str, str | None]:
    """Interpret a dotted token as a netmask or wildcard mask.

    Returns ``(prefix, style, note)``.  Only the two self-inverse values are
    ambiguous; ``0.0.0.0`` is treated as a wildcard (host match, /32) while
    ``255.255.255.255`` is treated as a netmask (/32), matching common
    operator usage.  Everything else is resolved by contiguity.
    """
    try:
        mask_addr = ipaddress.IPv4Address(token)
    except ipaddress.AddressValueError as exc:
        raise InputError(f"'{token}' is not a valid IPv4 mask.") from exc

    value = int(mask_addr)
    mask_prefix = _contiguous_prefix_from_mask(value, 32)
    wildcard_prefix = _contiguous_prefix_from_mask((~value) & 0xFFFFFFFF, 32)

    if value == 0:
        return 32, "wildcard", "0.0.0.0 read as a wildcard mask (host match)."
    if value == 0xFFFFFFFF:
        return 32, "dotted-mask", None

    if mask_prefix is not None and wildcard_prefix is None:
        return mask_prefix, "dotted-mask", None
    if wildcard_prefix is not None and mask_prefix is None:
        return wildcard_prefix, "wildcard", None
    if mask_prefix is not None and wildcard_prefix is not None:
        return mask_prefix, "dotted-mask", None
    raise InputError(
        f"Mask {token} is not contiguous. Use a contiguous mask such as "
        "255.255.255.0, or a wildcard such as 0.0.0.255."
    )


def _parse_prefix(token: str, version: int) -> tuple[int, str, str | None]:
    token = token.strip()
    if token.startswith("/"):
        token = token[1:]
    if not token:
        raise InputError("Missing prefix length after '/'.")
    if token.isdigit():
        prefix = int(token)
        if not 0 <= prefix <= MAX_PREFIX[version]:
            raise InputError(
                f"Prefix /{prefix} is out of range for IPv{version} "
                f"(0–{MAX_PREFIX[version]})."
            )
        return prefix, "cidr", None
    if version == 4:
        return _mask_from_dotted(token)
    raise InputError(
        f"'{token}' is not a valid IPv6 prefix. Use a number from 0 to 128."
    )


def parse_input(text: str) -> ParsedInput:
    """Parse a flexible address expression.

    Supported forms::

        10.0.0.5/24
        10.0.0.5 255.255.255.0
        10.0.0.5 0.0.0.255
        10.0.0.5/255.255.255.0
        2001:db8::1/64
        2001:db8::1
        10.0.0.5
    """

    raw = text or ""
    compact = " ".join(raw.strip().split())
    if not compact:
        raise InputError("Enter an address or network.")

    style = "cidr"
    note: str | None = None

    if len(compact.split()) > 1:
        parts = compact.split()
        if len(parts) != 2:
            raise InputError(
                "Too many values. Use 'address prefix', for example "
                "10.0.0.5 255.255.255.0."
            )
        address_text, prefix_text = parts
        if "/" in address_text:
            raise InputError(
                "Use either CIDR notation or a separate mask, not both. "
                "For example 10.0.0.5/24 or 10.0.0.5 255.255.255.0."
            )
        try:
            address = ipaddress.ip_address(address_text)
        except ValueError as exc:
            raise InputError(_address_error(address_text)) from exc
        if address.version != 4:
            raise InputError(
                "Dotted masks and wildcards only apply to IPv4. "
                "Use 2001:db8::1/64 for IPv6."
            )
        prefix, style, note = _parse_prefix(prefix_text, 4)
        had_prefix = True
    else:
        address_part, slash, prefix_part = compact.partition("/")
        try:
            address = ipaddress.ip_address(address_part)
        except ValueError as exc:
            if "-" in address_part and address_part.count("-") == 1:
                raise InputError(
                    "That looks like a range. Use the Range ↔ CIDR tool for "
                    "address ranges."
                ) from exc
            raise InputError(_address_error(address_part)) from exc

        if slash:
            prefix, style, note = _parse_prefix(prefix_part, address.version)
            had_prefix = True
        else:
            prefix = MAX_PREFIX[address.version]
            style = "bare"
            had_prefix = False

    network = ipaddress.ip_network((address, prefix), strict=False)
    host_bits_set = int(address) != int(network.network_address)

    return ParsedInput(
        raw=compact,
        address=address,
        network=network,
        prefixlen=prefix,
        version=address.version,
        had_prefix=had_prefix,
        host_bits_set=host_bits_set,
        style=style,
        note=note,
    )


def _address_error(token: str) -> str:
    return (
        f"Could not parse '{token}'. Try 10.0.0.0/24, "
        "10.0.0.5 255.255.255.0, or 2001:db8::/64."
    )


def parse_network(text: str, *, version: int | None = None) -> IPNetwork:
    """Parse one network expression and optionally enforce an IP version."""
    parsed = parse_input(text)
    if version is not None and parsed.version != version:
        raise InputError(f"Expected IPv{version}, got IPv{parsed.version}.")
    return parsed.network


def parse_network_lines(text: str) -> tuple[list[IPNetwork], list[str], list[str]]:
    """Parse one expression per line.

    Returns ``(networks, errors, warnings)``.  Blank lines and ``#`` comments
    are ignored so pasted firewall exports are easier to work with.
    """
    networks: list[IPNetwork] = []
    errors: list[str] = []
    warnings: list[str] = []
    for line_number, raw_line in enumerate((text or "").splitlines(), start=1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        try:
            parsed = parse_input(line)
        except InputError as exc:
            errors.append(f"Line {line_number}: {exc}")
            continue
        if parsed.host_bits_set:
            warnings.append(
                f"Line {line_number}: host bits set in {line}; "
                f"normalized to {parsed.normalized}."
            )
        networks.append(parsed.network)
    return networks, errors, warnings


def bulk_rows(text: str) -> tuple[list[dict[str, str]], list[str]]:
    """Parse one expression per line into table-ready rows."""
    rows: list[dict[str, str]] = []
    errors: list[str] = []
    for line_number, raw_line in enumerate((text or "").splitlines(), start=1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        try:
            parsed = parse_input(line)
        except InputError as exc:
            message = f"Line {line_number}: {exc}"
            errors.append(message)
            rows.append(
                {
                    "input": line,
                    "status": "error",
                    "family": "",
                    "normalized": "",
                    "network": "",
                    "prefix": "",
                    "mask": "",
                    "wildcard": "",
                    "first": "",
                    "last": "",
                    "usable": "",
                    "total": "",
                    "kind": "",
                    "notes": str(exc),
                }
            )
            continue

        info = host_info(parsed.network)
        row = {
            "input": line,
            "status": "normalized" if parsed.host_bits_set else "ok",
            "family": f"IPv{parsed.version}",
            "normalized": parsed.normalized,
            "network": str(parsed.network.network_address),
            "prefix": f"/{parsed.prefixlen}",
            "mask": parsed.netmask or "",
            "wildcard": parsed.wildcard or "",
            "first": str(info.first) if info.first is not None else "",
            "last": str(info.last) if info.last is not None else "",
            "usable": info.usable_label,
            "total": info.total_label,
            "kind": address_kind(parsed.address),
            "notes": (
                f"Host bits set; normalized to {parsed.normalized}"
                if parsed.host_bits_set
                else ""
            ),
        }
        rows.append(row)
    return rows, errors


def parse_address_list(text: str) -> tuple[list[IPAddress], list[str]]:
    """Parse one address per line, returning ``(addresses, errors)``."""
    addresses: list[IPAddress] = []
    errors: list[str] = []
    for line_number, raw_line in enumerate((text or "").splitlines(), start=1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        try:
            addresses.append(ipaddress.ip_address(line))
        except ValueError:
            errors.append(f"Line {line_number}: '{line}' is not an IP address.")
    return addresses, errors


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def format_int(value: int) -> str:
    return f"{value:,}"


def format_count(value: int) -> str:
    """Format an address/host count.

    Large powers of two are shown as powers of two as well as the full integer,
    which keeps IPv6 counts readable (and makes the number-format rule
    explicit).  Small values are formatted with thousands separators.
    """
    if value >= 65_536 and value > 0 and value & (value - 1) == 0:
        return f"2^{value.bit_length() - 1} = {value:,}"
    return f"{value:,}"


def format_bits(value: int, version: int) -> str:
    return format(value, f"0{BITS[version]}b")


def binary_groups(network: IPNetwork) -> list[str]:
    """Return the address bits grouped for display (octets or hextets)."""
    bits = format_bits(int(network.network_address), network.version)
    group_size = 8 if network.version == 4 else 16
    return [bits[i : i + group_size] for i in range(0, len(bits), group_size)]


def ipv6_slash64(prefixlen: int) -> tuple[int | None, str]:
    """Return the number of /64s in an IPv6 prefix, and a display label."""
    if prefixlen <= 64:
        count = 1 << (64 - prefixlen)
        return count, f"{format_count(count)} /64s"
    return None, f"1/{1 << (prefixlen - 64):,} of a /64"


@dataclass(frozen=True)
class HostInfo:
    total: int
    usable: int
    first: IPAddress | None
    last: IPAddress | None
    broadcast: IPv4Address | None
    note: str | None = None

    @property
    def total_label(self) -> str:
        return format_count(self.total)

    @property
    def usable_label(self) -> str:
        return format_count(self.usable)


def host_info(network: IPNetwork) -> HostInfo:
    """Return host semantics for a network, including /31 and /32 corner cases."""
    total = network.num_addresses
    if network.version == 4:
        if network.prefixlen == 32:
            return HostInfo(
                total=1,
                usable=1,
                first=network.network_address,
                last=network.network_address,
                broadcast=None,
                note="A /32 is a single host route; the address itself is usable.",
            )
        if network.prefixlen == 31:
            return HostInfo(
                total=2,
                usable=2,
                first=network.network_address,
                last=network.broadcast_address,
                broadcast=None,
                note=(
                    "RFC 3021 /31 point-to-point link: both addresses are usable "
                    "and there is no broadcast address."
                ),
            )
        return HostInfo(
            total=total,
            usable=max(0, total - 2),
            first=network.network_address + 1,
            last=network.broadcast_address - 1,
            broadcast=network.broadcast_address,
        )
    # IPv6 has no broadcast address.  The first address is the subnet-router
    # anycast address in practice, but all addresses are in the prefix.
    if network.prefixlen == 128:
        return HostInfo(
            total=1,
            usable=1,
            first=network.network_address,
            last=network.network_address,
            broadcast=None,
            note="A /128 is a single IPv6 address.",
        )
    if network.prefixlen == 127:
        note = "RFC 6164 /127 point-to-point link; both addresses are usable."
    else:
        note = (
            "IPv6 has no broadcast address. The first address is used as the "
            "subnet-router anycast address by convention."
        )
    return HostInfo(
        total=total,
        usable=total,
        first=network.network_address,
        last=network.broadcast_address,
        broadcast=None,
        note=note,
    )


def format_network_row(network: IPNetwork) -> dict[str, str]:
    """A display-friendly row used by tables and exports."""
    hosts = host_info(network)
    row: dict[str, str] = {
        "network": str(network),
        "version": f"IPv{network.version}",
        "prefix": f"/{network.prefixlen}",
        "first": str(hosts.first) if hosts.first is not None else "",
        "last": str(hosts.last) if hosts.last is not None else "",
        "usable": hosts.usable_label,
        "total": hosts.total_label,
        "broadcast": str(network.broadcast_address),
    }
    if network.version == 4:
        row["mask"] = str(network.netmask)
        row["wildcard"] = str(network.hostmask)
    else:
        row["mask"] = ""
        row["wildcard"] = ""
    return row


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AddressClass:
    label: str
    detail: str = ""
    tone: str = "gray"


_IPV4_RULES: tuple[tuple[str, str, str, str], ...] = (
    ("255.255.255.255/32", "Limited broadcast", "Reserved, all-hosts broadcast", "red"),
    ("0.0.0.0/8", "This network", "RFC 1122 'this network' block", "gray"),
    ("10.0.0.0/8", "RFC 1918 private", "Private-use address space", "green"),
    ("172.16.0.0/12", "RFC 1918 private", "Private-use address space", "green"),
    ("192.168.0.0/16", "RFC 1918 private", "Private-use address space", "green"),
    ("100.64.0.0/10", "CGNAT", "RFC 6598 shared address space (carrier-grade NAT)", "orange"),
    ("127.0.0.0/8", "Loopback", "RFC 1122 loopback", "violet"),
    ("169.254.0.0/16", "Link-local", "RFC 3927 link-local (APIPA)", "orange"),
    ("192.0.0.0/24", "IETF protocol assignments", "Special-purpose IPv4 block", "gray"),
    ("192.0.2.0/24", "Documentation", "TEST-NET-1 (RFC 5737)", "blue"),
    ("198.51.100.0/24", "Documentation", "TEST-NET-2 (RFC 5737)", "blue"),
    ("203.0.113.0/24", "Documentation", "TEST-NET-3 (RFC 5737)", "blue"),
    ("198.18.0.0/15", "Benchmarking", "RFC 2544 network interconnect benchmark", "gray"),
    ("192.88.99.0/24", "6to4 relay anycast", "Deprecated (RFC 7526)", "gray"),
    ("233.252.0.0/24", "Documentation multicast", "MCAST-TEST-NET (RFC 6676)", "blue"),
    ("224.0.0.0/4", "Multicast", "RFC 5771 multicast", "violet"),
    ("240.0.0.0/4", "Reserved", "Class E / future use", "red"),
)


_IPV6_RULES: tuple[tuple[str, str, str, str], ...] = (
    ("::/128", "Unspecified", "RFC 4291 unspecified address", "gray"),
    ("::1/128", "Loopback", "RFC 4291 loopback address", "violet"),
    ("::ffff:0:0/96", "IPv4-mapped", "IPv4-mapped IPv6 address", "orange"),
    ("64:ff9b::/96", "NAT64", "Well-known NAT64 prefix (RFC 6052)", "orange"),
    ("64:ff9b:1::/48", "NAT64 local-use", "Local-use NAT64 prefix (RFC 8215)", "orange"),
    ("100::/64", "Discard-only", "RFC 6666 discard-only prefix", "gray"),
    ("2001::/32", "Teredo", "Teredo tunneling (RFC 4380)", "gray"),
    ("2001:2::/48", "Benchmarking", "RFC 5180 benchmarking", "gray"),
    ("2001:db8::/32", "Documentation", "RFC 3849 documentation prefix", "blue"),
    ("2001:10::/28", "ORCHID", "Deprecated ORCHID (RFC 4843)", "gray"),
    ("2001:20::/28", "ORCHIDv2", "ORCHIDv2 (RFC 7343)", "gray"),
    ("2002::/16", "6to4", "6to4 tunneling (RFC 3056)", "gray"),
    ("3fff::/20", "Documentation", "RFC 9637 documentation prefix", "blue"),
    ("fc00::/7", "ULA", "Unique local address (RFC 4193)", "green"),
    ("fe80::/10", "Link-local", "RFC 4291 link-local unicast", "orange"),
    ("fec0::/10", "Site-local", "Deprecated site-local (RFC 3879)", "gray"),
    ("ff00::/8", "Multicast", "RFC 4291 multicast", "violet"),
    ("2000::/3", "GUA", "Global unicast address (RFC 4291)", "blue"),
)

_MULTICAST_SCOPES = {
    0: "reserved",
    1: "interface-local",
    2: "link-local",
    3: "realm-local",
    4: "admin-local",
    5: "site-local",
    8: "organization-local",
    14: "global",
    15: "reserved",
}


def _ipv4_scope(addr: IPv4Address) -> str:
    if addr.is_multicast:
        if addr in ipaddress.ip_network("224.0.0.0/24"):
            return "link-local scope"
        if addr in ipaddress.ip_network("239.0.0.0/8"):
            return "administratively scoped"
        return "multicast"
    return ""


def _ipv6_scope(addr: IPv6Address) -> str:
    if addr.is_multicast:
        scope = _MULTICAST_SCOPES.get((int(addr) >> 112) & 0xF, "unknown")
        return f"{scope} scope"
    if addr.is_link_local:
        return "link-local scope"
    if addr.is_loopback:
        return "host scope"
    return ""


def classify(addr: IPAddress) -> list[AddressClass]:
    """Classify an address, most-specific match first."""
    results: list[AddressClass] = []
    if addr.version == 4:
        for cidr, label, detail, tone in _IPV4_RULES:
            if addr in ipaddress.ip_network(cidr):
                extra = ""
                if label == "Multicast":
                    extra = f" · {_ipv4_scope(addr)}"
                results.append(AddressClass(label, detail + extra, tone))
        if not results:
            if addr.is_global:
                results.append(
                    AddressClass("Global unicast", "Publicly routable IPv4", "blue")
                )
            else:
                results.append(
                    AddressClass(
                        "Reserved / special", "No specific RFC block matched", "gray"
                    )
                )
        return results

    for cidr, label, detail, tone in _IPV6_RULES:
        if addr in ipaddress.ip_network(cidr):
            extra = ""
            if label == "Multicast":
                extra = f" · {_ipv6_scope(addr)}"
            if label == "IPv4-mapped":
                mapped = IPv4Address(int(addr) & 0xFFFFFFFF)
                extra = f" · {mapped}"
            results.append(AddressClass(label, detail + extra, tone))

    # IPv4-compatible ::/96 (deprecated) is inside ::/96 but not ::ffff:0:0/96.
    if not results and addr in ipaddress.ip_network("::/96"):
        results.append(
            AddressClass(
                "IPv4-compatible",
                "Deprecated IPv4-compatible IPv6 address (RFC 4291)",
                "gray",
            )
        )
    if not results:
        if addr.is_global:
            results.append(
                AddressClass("Global unicast", "Publicly routable IPv6", "blue")
            )
        elif addr.is_reserved:
            results.append(AddressClass("Reserved", "Reserved IPv6 space", "red"))
        else:
            results.append(
                AddressClass("Special", "No specific RFC block matched", "gray")
            )
    return results


def address_type_label(addr: IPAddress) -> str:
    return classify(addr)[0].label


def network_type_labels(network: IPNetwork) -> list[AddressClass]:
    """Classify both ends of a network and de-duplicate the labels."""
    seen: set[str] = set()
    merged: list[AddressClass] = []
    for addr in (network.network_address, network.broadcast_address):
        for item in classify(addr):
            if item.label not in seen:
                seen.add(item.label)
                merged.append(item)
    return merged


def address_kind(addr: IPAddress) -> str:
    """A short machine-friendly kind used in bulk tables/exports."""
    return classify(addr)[0].label


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------


def parsed_to_dict(parsed: ParsedInput) -> dict[str, object]:
    hosts = host_info(parsed.network)
    data: dict[str, object] = {
        "input": parsed.raw,
        "version": parsed.version,
        "address": str(parsed.address),
        "prefixlen": parsed.prefixlen,
        "normalized": parsed.normalized,
        "network": str(parsed.network.network_address),
        "last": str(parsed.network.broadcast_address),
        "first_usable": str(hosts.first) if hosts.first is not None else None,
        "last_usable": str(hosts.last) if hosts.last is not None else None,
        "total_addresses": hosts.total,
        "usable_addresses": hosts.usable,
        "host_bits_set": parsed.host_bits_set,
        "classification": [c.label for c in classify(parsed.address)],
    }
    if parsed.version == 4:
        data.update(
            {
                "broadcast": str(parsed.network.broadcast_address),
                "netmask": parsed.netmask,
                "wildcard": parsed.wildcard,
            }
        )
    else:
        data.update(
            {
                "compressed": str(parsed.address),
                "expanded": parsed.address.exploded,
                "network_start": str(parsed.network.network_address),
                "network_end": str(parsed.network.broadcast_address),
                "slash64_count": ipv6_slash64(parsed.prefixlen)[1],
            }
        )
    return data


def dedupe_classes(classes: Iterable[AddressClass]) -> list[AddressClass]:
    seen: set[str] = set()
    out: list[AddressClass] = []
    for item in classes:
        if item.label not in seen:
            seen.add(item.label)
            out.append(item)
    return out
