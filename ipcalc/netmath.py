"""Interval and prefix-list mathematics shared by the planning tools."""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable, Sequence
from typing import TypeAlias

from .core import IPAddress, IPNetwork, InputError

Interval: TypeAlias = tuple[int, int]


def network_interval(network: IPNetwork) -> Interval:
    return int(network.network_address), int(network.broadcast_address)


def network_version(networks: Sequence[IPNetwork]) -> int | None:
    versions = {n.version for n in networks}
    if len(versions) > 1:
        raise InputError("IPv4 and IPv6 networks cannot be mixed in one operation.")
    return versions.pop() if versions else None


def merge_ranges(ranges: Iterable[Interval]) -> list[Interval]:
    ordered = sorted((start, end) for start, end in ranges if start <= end)
    if not ordered:
        return []
    merged: list[Interval] = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end + 1:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def intersect_ranges(left: Iterable[Interval], right: Iterable[Interval]) -> list[Interval]:
    a = merge_ranges(left)
    b = merge_ranges(right)
    out: list[Interval] = []
    i = j = 0
    while i < len(a) and j < len(b):
        start = max(a[i][0], b[j][0])
        end = min(a[i][1], b[j][1])
        if start <= end:
            out.append((start, end))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return out


def subtract_ranges(base: Iterable[Interval], remove: Iterable[Interval]) -> list[Interval]:
    """Return ``base - remove`` as a minimal sorted interval list."""
    base_ranges = merge_ranges(base)
    remove_ranges = merge_ranges(remove)
    out: list[Interval] = []
    for start, end in base_ranges:
        cursor = start
        for remove_start, remove_end in remove_ranges:
            if remove_end < cursor:
                continue
            if remove_start > end:
                break
            if remove_start > cursor:
                out.append((cursor, min(end, remove_start - 1)))
            cursor = max(cursor, remove_end + 1)
            if cursor > end:
                break
        if cursor <= end:
            out.append((cursor, end))
    return out


def ranges_to_networks(ranges: Iterable[Interval], version: int) -> list[IPNetwork]:
    address_cls = ipaddress.IPv4Address if version == 4 else ipaddress.IPv6Address
    out: list[IPNetwork] = []
    for start, end in merge_ranges(ranges):
        out.extend(
            ipaddress.summarize_address_range(address_cls(start), address_cls(end))
        )
    return out


def networks_to_ranges(networks: Iterable[IPNetwork]) -> list[Interval]:
    return merge_ranges(network_interval(network) for network in networks)


def collapse_networks(networks: Iterable[IPNetwork]) -> list[IPNetwork]:
    nets = list(networks)
    if not nets:
        return []
    network_version(nets)
    return list(ipaddress.collapse_addresses(nets))


def coverage(networks: Iterable[IPNetwork]) -> int:
    return sum(end - start + 1 for start, end in networks_to_ranges(networks))


def union_networks(
    left: Iterable[IPNetwork], right: Iterable[IPNetwork] = ()
) -> list[IPNetwork]:
    nets = list(left) + list(right)
    return collapse_networks(nets)


def intersect_networks(
    left: Iterable[IPNetwork], right: Iterable[IPNetwork]
) -> list[IPNetwork]:
    left_nets = list(left)
    right_nets = list(right)
    version = network_version(left_nets + right_nets)
    if version is None:
        return []
    overlap = intersect_ranges(
        networks_to_ranges(left_nets), networks_to_ranges(right_nets)
    )
    return ranges_to_networks(overlap, version)


def subtract_networks(
    left: Iterable[IPNetwork], right: Iterable[IPNetwork]
) -> list[IPNetwork]:
    left_nets = list(left)
    right_nets = list(right)
    version = network_version(left_nets + right_nets)
    if version is None:
        return []
    remainder = subtract_ranges(
        networks_to_ranges(left_nets), networks_to_ranges(right_nets)
    )
    return ranges_to_networks(remainder, version)


def summarize_networks(networks: Iterable[IPNetwork]) -> dict[str, object]:
    """Collapse a list and report whether the summary covers extra space."""
    nets = list(networks)
    collapsed = collapse_networks(nets)
    input_coverage = coverage(nets)
    summarized_coverage = coverage(collapsed)
    version = network_version(nets)
    extra_ranges: list[IPNetwork] = []
    if version is not None and summarized_coverage > input_coverage:
        extra = subtract_ranges(
            networks_to_ranges(collapsed), networks_to_ranges(nets)
        )
        extra_ranges = ranges_to_networks(extra, version)
    return {
        "networks": collapsed,
        "input_coverage": input_coverage,
        "summarized_coverage": summarized_coverage,
        "extra": extra_ranges,
        "extra_count": max(0, summarized_coverage - input_coverage),
    }


def covering_supernet(networks: Iterable[IPNetwork]) -> IPNetwork | None:
    """The smallest single prefix that covers every supplied network."""
    nets = list(networks)
    if not nets:
        return None
    version = network_version(nets)
    assert version is not None
    start = min(int(net.network_address) for net in nets)
    end = max(int(net.broadcast_address) for net in nets)
    bits = 32 if version == 4 else 128
    differing = start ^ end
    prefix = bits - differing.bit_length() if differing else bits
    address_cls = ipaddress.IPv4Address if version == 4 else ipaddress.IPv6Address
    return ipaddress.ip_network((address_cls(start), prefix), strict=False)


def full_range(version: int) -> Interval:
    return 0, (1 << (32 if version == 4 else 128)) - 1


def invert_ranges(ranges: Iterable[Interval], version: int) -> list[Interval]:
    return subtract_ranges([full_range(version)], ranges)


def range_to_networks(
    start: IPAddress, end: IPAddress
) -> list[IPNetwork]:
    if start.version != end.version:
        raise InputError("The start and end addresses must use the same IP version.")
    if int(start) > int(end):
        raise InputError("The start address must not be greater than the end address.")
    return list(ipaddress.summarize_address_range(start, end))


def addr_in_network(addr: IPAddress, network: IPNetwork) -> bool:
    return addr.version == network.version and addr in network


def contains_network(outer: IPNetwork, inner: IPNetwork) -> bool:
    return outer.version == inner.version and inner.subnet_of(outer)


def overlap_relation(left: IPNetwork, right: IPNetwork) -> str:
    if left.version != right.version:
        return "different families"
    if left == right:
        return "identical"
    if not left.overlaps(right):
        return "disjoint"
    if left.subnet_of(right):
        return "right contains left"
    if right.subnet_of(left):
        return "left contains right"
    return "overlap"


def pairwise_relations(
    left: Iterable[IPNetwork], right: Iterable[IPNetwork], *, same_list: bool = False
) -> list[dict[str, str]]:
    left_list = list(left)
    right_list = list(right)
    rows: list[dict[str, str]] = []
    for index_a, first in enumerate(left_list):
        start_b = index_a if same_list else 0
        for index_b in range(start_b, len(right_list)):
            if same_list and index_a == index_b:
                continue
            second = right_list[index_b]
            relation = overlap_relation(first, second)
            if relation == "disjoint":
                continue
            rows.append(
                {
                    "left": str(first),
                    "right": str(second),
                    "relationship": relation,
                    "left_index": str(index_a + 1),
                    "right_index": str(index_b + 1),
                }
            )
    return rows


def largest_network(networks: Iterable[IPNetwork]) -> IPNetwork | None:
    nets = list(networks)
    if not nets:
        return None
    return max(nets, key=lambda net: (net.num_addresses, -int(net.network_address)))


def networks_from_text_lines(
    text: str, *, version: int | None = None
) -> tuple[list[IPNetwork], list[str], list[str]]:
    from .core import parse_network_lines

    nets, errors, warnings = parse_network_lines(text)
    if version is not None and any(net.version != version for net in nets):
        raise InputError(f"All networks must be IPv{version}.")
    return nets, errors, warnings
