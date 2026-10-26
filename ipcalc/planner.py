"""Subnet splitting, VLSM allocation, free-space, and IPAM helpers."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .core import (
    BITS,
    IPNetwork,
    InputError,
    format_count_compact,
    host_info,
    ipv6_slash64,
    parse_input,
)
from .netmath import (
    coverage,
    network_interval,
    subtract_networks,
)


@dataclass(frozen=True)
class Requirement:
    name: str
    hosts: int


@dataclass(frozen=True)
class Allocation:
    name: str
    requested_hosts: int
    network: IPNetwork | None
    usable: int = 0
    total: int = 0
    note: str = ""


@dataclass
class VLSMPlan:
    parent: IPNetwork
    allocations: list[Allocation] = field(default_factory=list)
    unallocated: list[Allocation] = field(default_factory=list)
    free: list[IPNetwork] = field(default_factory=list)

    @property
    def allocated_coverage(self) -> int:
        nets = [a.network for a in self.allocations if a.network is not None]
        return coverage(nets)

    @property
    def free_coverage(self) -> int:
        return coverage(self.free)

    @property
    def utilization(self) -> float:
        if self.parent.num_addresses == 0:
            return 0.0
        return self.allocated_coverage / self.parent.num_addresses


def ceil_log2(value: int) -> int:
    if value <= 1:
        return 0
    return (value - 1).bit_length()


def prefix_for_hosts(hosts: int, version: int) -> tuple[int, str]:
    """Smallest prefix that can hold ``hosts`` usable addresses.

    IPv4 follows the same rules as :func:`host_info`: /31 is two usable hosts
    (RFC 3021), /32 is one, and other prefixes lose two addresses to the
    network and broadcast addresses.  IPv6 has no broadcast address and uses
    all addresses in the prefix.
    """
    if hosts <= 0:
        raise InputError("Host count must be greater than zero.")
    if version == 4:
        maximum = (1 << 32) - 2
        if hosts > maximum:
            raise InputError(
                f"IPv4 cannot provide {hosts:,} usable hosts in one subnet "
                f"(maximum is {maximum:,})."
            )
        if hosts == 1:
            return 32, "single host (/32)"
        if hosts == 2:
            return 31, "RFC 3021 point-to-point (/31)"
        prefix = 32 - ceil_log2(hosts + 2)
        prefix = max(0, prefix)
        while prefix < 32 and host_info(ipaddress.ip_network((0, prefix))).usable < hosts:
            prefix -= 1
        return prefix, ""
    maximum = 1 << 128
    if hosts > maximum:
        raise InputError(
            f"IPv6 cannot provide {hosts:,} addresses in one prefix "
            f"(maximum is 2^128)."
        )
    prefix = 128 - ceil_log2(hosts)
    return max(0, prefix), ""


def hosts_for_prefix(prefixlen: int, version: int) -> int:
    address = ipaddress.IPv4Address(0) if version == 4 else ipaddress.IPv6Address(0)
    network = ipaddress.ip_network((address, prefixlen), strict=False)
    return host_info(network).usable


def subnet_count(parent_prefix: int, child_prefix: int) -> int:
    if child_prefix < parent_prefix:
        raise InputError("The child prefix must be longer than the parent prefix.")
    return 1 << (child_prefix - parent_prefix)


def split_by_prefix(
    network: IPNetwork, new_prefix: int, *, limit: int = 4096
) -> list[IPNetwork]:
    if not network.prefixlen <= new_prefix <= BITS[network.version]:
        raise InputError(
            f"New prefix /{new_prefix} must be between /{network.prefixlen} "
            f"and /{BITS[network.version]}."
        )
    count = subnet_count(network.prefixlen, new_prefix)
    if count > limit:
        raise InputError(
            f"That split creates {count:,} subnets. The limit is {limit:,} — "
            "use a shorter prefix or raise the limit."
        )
    return list(network.subnets(new_prefix=new_prefix))


@dataclass(frozen=True)
class SplitResult:
    networks: list[IPNetwork]
    new_prefix: int
    note: str = ""


def split_by_count(
    network: IPNetwork, count: int, *, limit: int = 4096
) -> SplitResult:
    if count <= 0:
        raise InputError("Number of subnets must be greater than zero.")
    bits = ceil_log2(count)
    new_prefix = network.prefixlen + bits
    if new_prefix > BITS[network.version]:
        raise InputError(
            f"Cannot create {count:,} subnets in {network}; only "
            f"{1 << (BITS[network.version] - network.prefixlen):,} fit."
        )
    actual = 1 << bits
    note = ""
    if actual != count:
        note = (
            f"{count:,} rounded up to {actual:,} subnets because subnet counts "
            "must be a power of two."
        )
    return SplitResult(
        split_by_prefix(network, new_prefix, limit=limit),
        new_prefix,
        note,
    )


def split_by_hosts(
    network: IPNetwork, min_hosts: int, *, limit: int = 4096
) -> SplitResult:
    prefix, prefix_note = prefix_for_hosts(min_hosts, network.version)
    if prefix < network.prefixlen:
        raise InputError(
            f"{min_hosts:,} hosts needs a /{prefix}, which is larger than the "
            f"parent {network}."
        )
    count = subnet_count(network.prefixlen, prefix)
    if count > limit:
        raise InputError(
            f"That requirement creates {count:,} subnets. The limit is "
            f"{limit:,}."
        )
    note_parts = []
    if prefix_note:
        note_parts.append(prefix_note)
    note_parts.append(
        f"Each /{prefix} has {format_count_compact(hosts_for_prefix(prefix, network.version))} "
        "usable addresses."
    )
    return SplitResult(
        list(network.subnets(new_prefix=prefix)),
        prefix,
        " ".join(note_parts),
    )


def split_table(networks: Iterable[IPNetwork]) -> list[dict[str, str]]:
    from .core import format_network_row

    rows = []
    for index, network in enumerate(networks, start=1):
        row = format_network_row(network)
        rows.append(
            {
                "#": str(index),
                "network": row["network"],
                "first": row["first"],
                "last": row["last"],
                "usable": row["usable"],
                "total": row["total"],
                "mask": row["mask"],
                "wildcard": row["wildcard"],
                "broadcast": row["broadcast"],
            }
        )
    return rows


def vlsm_plan(
    parent: IPNetwork, requirements: Sequence[Requirement]
) -> VLSMPlan:
    """Largest-first, next-fit VLSM allocation.

    Because every block size is a power of two and the parent starts on its own
    boundary, each aligned allocation keeps the next free address aligned for
    every smaller block.  No space is lost to alignment gaps.
    """
    version = parent.version
    plan = VLSMPlan(parent=parent)
    ordered = sorted(
        enumerate(requirements), key=lambda item: (-item[1].hosts, item[0])
    )
    next_start = int(parent.network_address)
    parent_end = int(parent.broadcast_address)

    for _, requirement in ordered:
        if requirement.hosts <= 0:
            plan.unallocated.append(
                Allocation(
                    requirement.name,
                    requirement.hosts,
                    None,
                    note="Host count must be greater than zero.",
                )
            )
            continue
        try:
            prefix, prefix_note = prefix_for_hosts(requirement.hosts, version)
        except InputError as exc:
            plan.unallocated.append(
                Allocation(requirement.name, requirement.hosts, None, note=str(exc))
            )
            continue
        if prefix < parent.prefixlen:
            plan.unallocated.append(
                Allocation(
                    requirement.name,
                    requirement.hosts,
                    None,
                    note=(
                        f"Needs a /{prefix}, which is larger than the parent "
                        f"/{parent.prefixlen}."
                    ),
                )
            )
            continue

        size = 1 << (BITS[version] - prefix)
        start = next_start
        if start + size - 1 > parent_end:
            plan.unallocated.append(
                Allocation(
                    requirement.name,
                    requirement.hosts,
                    None,
                    note="No contiguous space left in the parent block.",
                )
            )
            continue

        network = ipaddress.ip_network((start, prefix), strict=False)
        info = host_info(network)
        plan.allocations.append(
            Allocation(
                requirement.name,
                requirement.hosts,
                network,
                usable=info.usable,
                total=info.total,
                note=prefix_note,
            )
        )
        next_start = start + size

    allocated = [a.network for a in plan.allocations if a.network is not None]
    plan.free = subtract_networks([parent], allocated)
    return plan


def free_space(
    parent: IPNetwork, used: Sequence[IPNetwork]
) -> tuple[list[IPNetwork], list[str]]:
    """Return free gaps inside ``parent`` and warnings about the used list."""
    warnings: list[str] = []
    inside: list[IPNetwork] = []
    for network in used:
        if network.version != parent.version:
            warnings.append(f"{network} is a different IP version; ignored.")
            continue
        if not network.subnet_of(parent):
            warnings.append(f"{network} is outside {parent}; ignored.")
            continue
        inside.append(network)

    ordered = sorted(inside, key=lambda net: (int(net.network_address), net.prefixlen))
    for previous, current in zip(ordered, ordered[1:]):
        if int(current.network_address) <= int(previous.broadcast_address):
            warnings.append(
                f"{current} overlaps {previous}; overlapping space is counted "
                "once."
            )
    gaps = subtract_networks([parent], inside)
    return gaps, warnings


@dataclass(frozen=True)
class IPAMSegment:
    label: str
    network: IPNetwork
    kind: str  # "allocated" or "free"
    start_pct: float
    width_pct: float
    addresses: int


def ipam_segments(
    parent: IPNetwork, allocations: Sequence[tuple[str, IPNetwork]]
) -> tuple[list[IPAMSegment], list[str]]:
    """Build proportional segments for an IPAM bar, clipping to the parent."""
    warnings: list[str] = []
    parent_start, parent_end = network_interval(parent)
    total = parent_end - parent_start + 1

    usable: list[tuple[str, IPNetwork]] = []
    for label, network in allocations:
        if network.version != parent.version:
            warnings.append(f"{network} is a different IP version; ignored.")
            continue
        if not network.subnet_of(parent):
            warnings.append(f"{network} is outside {parent}; ignored.")
            continue
        usable.append((label or str(network), network))

    usable.sort(key=lambda item: (int(item[1].network_address), item[1].prefixlen))
    segments: list[IPAMSegment] = []
    cursor = parent_start
    for label, network in usable:
        start, end = network_interval(network)
        if start < cursor:
            warnings.append(f"{network} overlaps an earlier allocation; clipped.")
            start = cursor
        if start > cursor:
            for gap_net in _range_to_label_range(cursor, start - 1, parent.version):
                segments.append(
                    _make_segment("Free", gap_net, "free", parent_start, total)
                )
        if start > parent_end:
            break
        start = max(start, cursor)
        end = min(end, parent_end)
        if start > end:
            continue
        for piece in _range_to_label_range(start, end, parent.version):
            segments.append(
                _make_segment(label, piece, "allocated", parent_start, total)
            )
        cursor = max(cursor, end + 1)

    if cursor <= parent_end:
        for gap_net in _range_to_label_range(cursor, parent_end, parent.version):
            segments.append(
                _make_segment("Free", gap_net, "free", parent_start, total)
            )

    if not segments:
        segments.append(_make_segment("Free", parent, "free", parent_start, total))
    return segments, warnings


def _range_to_label_range(start: int, end: int, version: int) -> list[IPNetwork]:
    address_cls = ipaddress.IPv4Address if version == 4 else ipaddress.IPv6Address
    return list(
        ipaddress.summarize_address_range(address_cls(start), address_cls(end))
    )


def _make_segment(
    label: str,
    network: IPNetwork,
    kind: str,
    parent_start: int,
    total: int,
) -> IPAMSegment:
    start, end = network_interval(network)
    return IPAMSegment(
        label=label,
        network=network,
        kind=kind,
        start_pct=(start - parent_start) / total * 100,
        width_pct=(end - start + 1) / total * 100,
        addresses=end - start + 1,
    )


def allocation_rows(plan: VLSMPlan) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for allocation in plan.allocations:
        if allocation.network is None:
            continue
        info = host_info(allocation.network)
        row = {
            "name": allocation.name,
            "requested": format_count_compact(allocation.requested_hosts),
            "cidr": str(allocation.network),
            "prefix": f"/{allocation.network.prefixlen}",
            "first": str(info.first) if info.first is not None else "",
            "last": str(info.last) if info.last is not None else "",
            "usable": format_count_compact(info.usable),
            "total": format_count_compact(info.total),
            "utilization": (
                f"{allocation.requested_hosts / info.usable:.0%}"
                if info.usable
                else ""
            ),
        }
        if allocation.network.version == 4:
            row["mask"] = str(allocation.network.netmask)
            row["wildcard"] = str(allocation.network.hostmask)
            row["broadcast"] = (
                str(allocation.network.broadcast_address)
                if allocation.network.prefixlen <= 30
                else ""
            )
        else:
            row["mask"] = ""
            row["wildcard"] = ""
            row["broadcast"] = ""
        rows.append(row)
    return rows


def plan_payload(
    parent: IPNetwork,
    requirements: Sequence[Requirement],
    plan: VLSMPlan,
) -> dict[str, object]:
    """A portable JSON representation of a plan."""
    return {
        "schema": "ip-subnet-calculator/plan/v1",
        "parent": str(parent),
        "ip_version": parent.version,
        "requirements": [
            {"name": req.name, "hosts": req.hosts} for req in requirements
        ],
        "allocations": [
            {
                "name": allocation.name,
                "requested_hosts": allocation.requested_hosts,
                "cidr": str(allocation.network) if allocation.network else None,
                "usable": allocation.usable,
                "total": allocation.total,
            }
            for allocation in plan.allocations
        ],
        "unallocated": [
            {
                "name": allocation.name,
                "requested_hosts": allocation.requested_hosts,
                "reason": allocation.note,
            }
            for allocation in plan.unallocated
        ],
        "free": [
            {
                "cidr": str(network),
                "addresses": network.num_addresses,
            }
            for network in plan.free
        ],
    }


def parse_plan_payload(payload: dict[str, object]) -> tuple[str, list[tuple[str, int]]]:
    """Validate an imported plan and return ``(parent, requirements)``."""
    if not isinstance(payload, dict):
        raise InputError("Plan JSON must be an object.")
    parent = payload.get("parent")
    if not isinstance(parent, str):
        raise InputError("Plan JSON is missing a 'parent' string.")
    parse_input(parent)
    raw_requirements = payload.get("requirements", [])
    if not isinstance(raw_requirements, list):
        raise InputError("Plan JSON 'requirements' must be a list.")
    requirements: list[tuple[str, int]] = []
    for index, item in enumerate(raw_requirements, start=1):
        if not isinstance(item, dict):
            raise InputError(f"Requirement {index} is not an object.")
        name = str(item.get("name") or f"Requirement {index}")
        hosts = item.get("hosts")
        if not isinstance(hosts, int) or hosts <= 0:
            raise InputError(f"Requirement {index} needs a positive integer 'hosts'.")
        requirements.append((name, hosts))
    return parent, requirements


def plan_allocation_rows(payload: dict[str, object]) -> list[dict[str, str]]:
    raw = payload.get("allocations", [])
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, str]] = []
    for item in raw:
        if isinstance(item, dict):
            rows.append(
                {
                    "name": str(item.get("name", "")),
                    "cidr": str(item.get("cidr", "")),
                    "hosts": str(item.get("requested_hosts", "")),
                }
            )
    return rows


# ---------------------------------------------------------------------------
# IPv6 site planning
# ---------------------------------------------------------------------------


def site_plan(parent: IPNetwork, allocations: Sequence[tuple[str, IPNetwork]]):
    """Allocate /56 sites inside a /48 and show the /64 capacity."""
    if parent.version != 6 or parent.prefixlen != 48:
        raise InputError("The site planner expects an IPv6 /48 parent block.")
    sites = list(parent.subnets(new_prefix=56))
    used: list[tuple[str, IPNetwork]] = []
    warnings: list[str] = []
    for label, network in allocations:
        if network.version != 6:
            warnings.append(f"{network} is not IPv6; ignored.")
            continue
        if network.prefixlen != 56:
            warnings.append(f"{network} is not a /56; ignored.")
            continue
        if not network.subnet_of(parent):
            warnings.append(f"{network} is outside {parent}; ignored.")
            continue
        used.append((label, network))
    free = [site for site in sites if not any(site.overlaps(net) for _, net in used)]
    return {
        "sites": sites,
        "used": used,
        "free": free,
        "warnings": warnings,
        "total_sites": len(sites),
        "used_sites": len(used),
        "free_sites": len(free),
        "slash64_per_site": 256,
        "total_slash64": int(len(sites)) * 256,
    }


def slash64_label(network: IPNetwork) -> str:
    return ipv6_slash64(network.prefixlen)[1]
