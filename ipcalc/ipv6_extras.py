"""IPv6 extras: EUI-64, solicited-node multicast, and NAT64."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass

from .core import IPv6Address, IPv6Network, InputError


@dataclass(frozen=True)
class MacInfo:
    raw: str
    normalized: str
    octets: bytes
    multicast: bool
    locally_administered: bool


def parse_mac(value: str) -> MacInfo:
    """Parse common MAC address formats into six octets."""
    compact = re.sub(r"[\s:.\-]", "", value or "")
    if not re.fullmatch(r"[0-9a-fA-F]{12}", compact):
        raise InputError(
            "Enter a 48-bit MAC address such as aa:bb:cc:dd:ee:ff, "
            "aa-bb-cc-dd-ee-ff, or aabb.ccdd.eeff."
        )
    octets = bytes.fromhex(compact)
    return MacInfo(
        raw=value,
        normalized=":".join(f"{byte:02x}" for byte in octets),
        octets=octets,
        multicast=bool(octets[0] & 0x01),
        locally_administered=bool(octets[0] & 0x02),
    )


def eui64_from_mac(mac: MacInfo) -> bytes:
    """Modified EUI-64: flip the U/L bit and insert ff:fe in the middle."""
    first = mac.octets[0] ^ 0x02
    return bytes([first]) + mac.octets[1:3] + b"\xff\xfe" + mac.octets[3:]


def eui64_display(eui: bytes) -> str:
    words = [f"{int.from_bytes(eui[i : i + 2], 'big'):04x}" for i in range(0, 8, 2)]
    return ":".join(words)


def mac_from_eui64(eui: bytes) -> MacInfo:
    if len(eui) != 8:
        raise InputError("A modified EUI-64 value must be 8 bytes.")
    mac = bytes([eui[0] ^ 0x02]) + eui[1:3] + eui[5:8]
    return MacInfo(
        raw="",
        normalized=":".join(f"{byte:02x}" for byte in mac),
        octets=mac,
        multicast=bool(mac[0] & 0x01),
        locally_administered=bool(mac[0] & 0x02),
    )


@dataclass(frozen=True)
class SlaacResult:
    interface_id: str
    address: IPv6Address
    link_local: IPv6Address
    note: str | None


def slaac_from_mac(prefix: IPv6Network, mac: MacInfo) -> SlaacResult:
    if prefix.version != 6:
        raise InputError("EUI-64 SLAAC requires an IPv6 prefix.")
    eui = eui64_from_mac(mac)
    interface_id = int.from_bytes(eui, "big")
    if prefix.prefixlen == 64:
        address = IPv6Address(int(prefix.network_address) | interface_id)
        note = None
    else:
        # Show the illustrative address anyway, but be explicit that SLAAC is
        # defined for /64 prefixes.
        address = IPv6Address(int(prefix.network_address) | interface_id)
        note = (
            "SLAAC is defined for /64 prefixes. This is an illustrative "
            "combination of the supplied prefix and the EUI-64 interface ID."
        )
    link_local = IPv6Address(int(ipaddress.IPv6Address("fe80::")) | interface_id)
    return SlaacResult(
        interface_id=eui64_display(eui),
        address=address,
        link_local=link_local,
        note=note,
    )


def solicited_node(addr: IPv6Address) -> IPv6Address:
    base = int(ipaddress.IPv6Address("ff02::1:ff00:0"))
    return IPv6Address(base | (int(addr) & 0xFFFFFF))


def solicited_node_mac(addr: IPv6Address) -> str:
    last24 = int(addr) & 0xFFFFFF
    octets = last24.to_bytes(3, "big")
    return f"33:33:{octets[0]:02x}:{octets[1]:02x}:{octets[2]:02x}"


def nat64_map(ipv4: ipaddress.IPv4Address, prefix: IPv6Network) -> IPv6Address:
    if prefix.version != 6 or prefix.prefixlen != 96:
        raise InputError(
            "The simplified NAT64 mapping here uses a /96 prefix, for example "
            "64:ff9b::/96."
        )
    return IPv6Address(int(prefix.network_address) | int(ipv4))


def nat64_extract(addr: IPv6Address, prefix: IPv6Network) -> ipaddress.IPv4Address | None:
    if prefix.prefixlen != 96:
        raise InputError("NAT64 extraction uses a /96 prefix.")
    if addr not in prefix:
        return None
    return ipaddress.IPv4Address(int(addr) & 0xFFFFFFFF)


def eui64_from_address(addr: IPv6Address) -> tuple[bytes, bool] | None:
    """Return the EUI-64 interface ID if the address contains one."""
    interface = int(addr) & ((1 << 64) - 1)
    eui = interface.to_bytes(8, "big")
    if eui[3:5] == b"\xff\xfe":
        return eui, True
    return eui, False


def site_slash64s(site: IPv6Network) -> list[IPv6Network]:
    if site.prefixlen > 64:
        raise InputError("A site prefix must be /64 or shorter.")
    count = 1 << (64 - site.prefixlen)
    if count > 65_536:
        raise InputError("That site prefix contains more than 65,536 /64s; use a /48.")
    return list(site.subnets(new_prefix=64))
