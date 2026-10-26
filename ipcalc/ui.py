"""Shared Streamlit UI helpers.

Native widgets are used wherever possible.  Custom components are reserved for
the two things Streamlit has no native equivalent for: click-to-copy fields and
the bit/IPAM visualisations.
"""

from __future__ import annotations

import csv
import io
import json
import re
from typing import Any, Iterable, Sequence

import ipaddress
import pandas as pd
import streamlit as st

from .components import binary_view, copy_button, copy_field, ipam_bar
from .core import (
    AddressClass,
    IPNetwork,
    InputError,
    ParsedInput,
    classify,
    format_count,
    format_count_compact,
    format_network_row,
    host_info,
    ipv6_slash64,
    parse_input,
    parse_network_lines,
    parsed_to_dict,
)


def page_header(title: str, subtitle: str, *, icon: str) -> None:
    st.title(title, icon=icon)
    st.caption(subtitle)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "value"


def field_key(prefix: str, label: str) -> str:
    return f"{prefix}-{slugify(label)}"


def field_grid(
    fields: Sequence[tuple[str, Any]],
    *,
    key_prefix: str,
    columns: int = 3,
) -> None:
    """Render click-to-copy fields in a responsive grid."""
    items = [(label, value) for label, value in fields]
    for start in range(0, len(items), columns):
        chunk = items[start : start + columns]
        cols = st.columns(len(chunk))
        for col, (label, value) in zip(cols, chunk):
            with col:
                copy_field(
                    label,
                    "—" if value is None or value == "" else value,
                    key=field_key(key_prefix, label),
                )


def render_badges(classes: Iterable[AddressClass]) -> None:
    items = list(classes)
    if not items:
        return
    with st.container(horizontal=True):
        for item in items:
            st.badge(item.label, color=item.tone, help=item.detail or None)


def input_error(exc: Exception) -> None:
    st.error(str(exc), icon=":material/error:")


def show_messages(errors: Iterable[str], warnings: Iterable[str] = ()) -> None:
    errors = list(errors)
    warnings = list(warnings)
    if errors:
        if len(errors) == 1:
            st.error(errors[0], icon=":material/error:")
        else:
            st.error(
                f"{len(errors)} input lines could not be parsed.",
                icon=":material/error:",
            )
            with st.expander("Show parse errors", expanded=True):
                for error in errors:
                    st.write(error)
    if warnings:
        if len(warnings) == 1:
            st.warning(warnings[0], icon=":material/warning:")
        else:
            st.warning(
                f"{len(warnings)} input lines were normalized or ignored.",
                icon=":material/warning:",
            )
            with st.expander("Show warnings"):
                for warning in warnings:
                    st.write(warning)


def rows_to_csv(rows: Sequence[dict[str, Any]]) -> str:
    if not rows:
        return ""
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def download_csv(
    rows: Sequence[dict[str, Any]],
    filename: str,
    *,
    key: str,
    label: str = "Download CSV",
) -> None:
    st.download_button(
        label,
        rows_to_csv(rows),
        file_name=filename,
        mime="text/csv",
        icon=":material/download:",
        width="content",
        key=key,
        disabled=not rows,
    )


def download_json(
    payload: dict[str, Any],
    filename: str,
    *,
    key: str,
    label: str = "Download JSON",
) -> None:
    st.download_button(
        label,
        json.dumps(payload, indent=2, default=str),
        file_name=filename,
        mime="application/json",
        icon=":material/download:",
        width="content",
        key=key,
        disabled=not payload,
    )


def copy_and_download(
    *,
    payload: dict[str, Any] | None,
    rows: Sequence[dict[str, Any]],
    key_prefix: str,
    filename: str,
    include_downloads: bool = True,
) -> None:
    """Copy-as-JSON/CSV buttons plus optional file downloads."""
    json_text = json.dumps(payload, indent=2, default=str) if payload else ""
    csv_text = rows_to_csv(rows)
    with st.container(horizontal=True):
        if payload:
            copy_button("Copy JSON", json_text, key=f"{key_prefix}-copy-json")
        copy_button("Copy CSV", csv_text, key=f"{key_prefix}-copy-csv")
        if include_downloads and rows:
            download_csv(rows, f"{filename}.csv", key=f"{key_prefix}-download-csv")
        if include_downloads and payload:
            download_json(payload, f"{filename}.json", key=f"{key_prefix}-download-json")


def table_columns() -> dict[str, str]:
    return {
        "#": "#",
        "network": "Network",
        "version": "Version",
        "prefix": "Prefix",
        "first": "First usable",
        "last": "Last usable",
        "usable": "Usable",
        "total": "Total",
        "mask": "Mask",
        "wildcard": "Wildcard",
        "broadcast": "Broadcast",
        "kind": "Kind",
        "name": "Name",
        "requested": "Requested",
        "cidr": "CIDR",
        "utilization": "Utilization",
        "relationship": "Relationship",
        "left": "Left",
        "right": "Right",
        "address": "Address",
        "contains": "Contains",
        "notes": "Notes",
        "provider": "Provider",
        "supported": "Supported",
        "reserved": "Reserved",
        "first_usable": "First usable",
        "last_usable": "Last usable",
        "usage": "Usage",
        "count": "Count",
        "free": "Free",
        "start": "Start",
        "end": "End",
        "addresses": "Addresses",
        "input": "Input",
        "status": "Status",
        "family": "Family",
        "normalized": "Normalized",
        "slash64": "/64s",
        "first64": "First /64",
        "last64": "Last /64",
        "slash64s": "/64s per site",
        "pointer": "Pointer",
        "target": "Target",
        "reason": "Reason",
    }


def display_rows(
    rows: Sequence[dict[str, Any]], *, columns: Sequence[str] | None = None
) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    if columns is not None:
        keep = [column for column in columns if column in frame.columns]
        frame = frame[keep]
    frame = frame.rename(columns=table_columns())
    # Hide columns that are empty for every row (for example IPv6 mask
    # columns), but always keep the row number.
    empty = [
        column
        for column in frame.columns
        if column != "#"
        and (frame[column].fillna("").astype(str).str.strip() == "").all()
    ]
    return frame.drop(columns=empty)


def network_rows(networks: Iterable[IPNetwork], *, numbered: bool = True) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index, network in enumerate(networks, start=1):
        row = format_network_row(network)
        if numbered:
            row = {"#": str(index), **row}
        rows.append(row)
    return rows


def network_table(
    networks: Iterable[IPNetwork],
    *,
    key: str,
    height: int | str | None = None,
    caption: str | None = None,
    alt: str = "Table of IP networks",
) -> None:
    rows = network_rows(networks)
    if not rows:
        st.info("No networks to show.", icon=":material/info:")
        return
    frame = display_rows(rows)
    kwargs: dict[str, Any] = {}
    if height is not None:
        kwargs["height"] = height
    st.dataframe(
        frame,
        hide_index=True,
        width="stretch",
        key=key,
        alt=alt,
        **kwargs,
    )
    if caption:
        st.caption(caption)


def parse_one(text: str) -> ParsedInput | None:
    try:
        return parse_input(text)
    except InputError as exc:
        input_error(exc)
        return None


def parse_list(
    text: str,
    *,
    empty_message: str = "Paste at least one network.",
    same_family: bool = False,
) -> list[IPNetwork] | None:
    networks, errors, warnings = parse_network_lines(text)
    show_messages(errors, warnings)
    if errors:
        return None
    if not networks:
        st.info(empty_message, icon=":material/info:")
        return None
    if same_family and len({network.version for network in networks}) > 1:
        st.error(
            "This operation needs networks from a single address family. "
            "Split IPv4 and IPv6 into separate runs.",
            icon=":material/error:",
        )
        return None
    return networks


def style_label(parsed: ParsedInput) -> str:
    return {
        "cidr": "CIDR",
        "dotted-mask": "Dotted netmask",
        "wildcard": "Wildcard mask",
        "bare": "Bare address",
    }.get(parsed.style, parsed.style)


def result_fields(parsed: ParsedInput) -> list[tuple[str, Any]]:
    info = host_info(parsed.network)
    network = parsed.network
    if parsed.version == 4:
        return [
            ("Normalized CIDR", str(network)),
            ("Network address", str(network.network_address)),
            (
                "Broadcast address",
                str(network.broadcast_address) if parsed.prefixlen <= 30 else "—",
            ),
            ("First usable host", str(info.first) if info.first else "—"),
            ("Last usable host", str(info.last) if info.last else "—"),
            ("Usable hosts", info.usable_label),
            ("Total addresses", info.total_label),
            ("Netmask", parsed.netmask),
            ("Wildcard mask", parsed.wildcard),
            ("Prefix length", f"/{parsed.prefixlen}"),
            ("Input address", str(parsed.address)),
            ("Input format", style_label(parsed)),
        ]
    classes = ", ".join(item.label for item in classify(parsed.address))
    return [
        ("Normalized CIDR", str(network)),
        ("Compressed address", str(parsed.address)),
        ("Expanded address", parsed.address.exploded),
        ("Network start", str(network.network_address)),
        ("Network end", str(network.broadcast_address)),
        ("Address type", classes),
        ("/64 count", ipv6_slash64(parsed.prefixlen)[1]),
        ("Usable addresses", info.usable_label),
        ("Total addresses", info.total_label),
        ("Prefix length", f"/{parsed.prefixlen}"),
        ("Input address", str(parsed.address)),
        ("Input format", style_label(parsed)),
    ]


def binary_labels(version: int) -> list[str]:
    if version == 4:
        return [f"octet {index}" for index in range(1, 5)]
    return [f"hextet {index}" for index in range(1, 9)]


def render_result(parsed: ParsedInput, *, key_prefix: str = "result") -> None:
    if parsed.host_bits_set:
        st.warning(
            f"Host bits are set in **{parsed.raw}**. The usable network is "
            f"**{parsed.normalized}** — results below use the normalized network.",
            icon=":material/warning:",
        )
    if parsed.note:
        st.info(parsed.note, icon=":material/info:")

    render_badges(classify(parsed.address))
    st.space("small")

    field_grid(result_fields(parsed), key_prefix=key_prefix, columns=3)

    info = host_info(parsed.network)
    if info.note:
        st.caption(info.note)

    with st.container(border=True):
        st.subheader("Binary view")
        st.caption(
            "Blue bits are the network portion; grey bits are the host portion. "
            f"The boundary is after bit {parsed.prefixlen}."
        )
        binary_view(
            format(int(parsed.network.network_address), f"0{32 if parsed.version == 4 else 128}b"),
            prefixlen=parsed.prefixlen,
            version=parsed.version,
            group_labels=binary_labels(parsed.version),
            key=f"{key_prefix}-binary",
        )

    payload = parsed_to_dict(parsed)
    rows = [format_network_row(parsed.network)]
    copy_and_download(
        payload=payload,
        rows=rows,
        key_prefix=key_prefix,
        filename=f"subnet-{slugify(parsed.normalized)}",
        include_downloads=False,
    )


# ---------------------------------------------------------------------------
# Cheat sheet
# ---------------------------------------------------------------------------


def _v4_network(prefix: int) -> ipaddress.IPv4Network:
    return ipaddress.ip_network((ipaddress.IPv4Address(0), prefix), strict=False)


def _v6_network(prefix: int) -> ipaddress.IPv6Network:
    return ipaddress.ip_network((ipaddress.IPv6Address(0), prefix), strict=False)


def v4_cheat_rows() -> list[dict[str, str]]:
    rows = []
    for prefix in range(32, -1, -1):
        network = _v4_network(prefix)
        info = host_info(network)
        note = ""
        if prefix == 31:
            note = "RFC 3021 · 2 usable"
        elif prefix == 32:
            note = "Single host"
        elif prefix == 0:
            note = "Default route"
        elif prefix == 24:
            note = "Classic /24"
        rows.append(
            {
                "prefix": f"/{prefix}",
                "mask": str(network.netmask),
                "wildcard": str(network.hostmask),
                "total": format_count(info.total),
                "usable": format_count(info.usable),
                "notes": note,
            }
        )
    return rows


def v6_cheat_rows() -> list[dict[str, str]]:
    common = {0, 16, 29, 32, 40, 44, 48, 52, 56, 60, 64, 96, 112, 120, 124, 127, 128}
    notes = {
        0: "Default route",
        16: "Large ISP allocation",
        29: "Typical mobile /29 assignment",
        32: "ISP allocation",
        40: "Large site",
        44: "Site",
        48: "Site / global routing prefix",
        52: "Site subdivision",
        56: "Small site / residential",
        60: "Small network",
        64: "Single LAN; SLAAC",
        96: "NAT64 well-known prefix length",
        112: "Small point-to-point style block",
        120: "Very small network",
        124: "Tiny network",
        127: "RFC 6164 point-to-point",
        128: "Single host",
    }
    rows = []
    for prefix in sorted(common):
        network = _v6_network(prefix)
        info = host_info(network)
        rows.append(
            {
                "prefix": f"/{prefix}",
                "addresses": format_count_compact(info.total),
                "slash64": ipv6_slash64(prefix)[1],
                "notes": notes.get(prefix, ""),
            }
        )
    return rows


def render_cheat_sheet(
    *, key_prefix: str = "cheat", max_height: int = 1200
) -> None:
    st.caption(
        "IPv4 rows run from /32 down to /0, so the most common host masks are "
        "at the top. Usable-host counts subtract the network and broadcast "
        "addresses except for /31 (RFC 3021) and /32. IPv6 has no broadcast "
        "address; large counts are shown as powers of two (or scientific "
        "notation when the value is not a power of two)."
    )
    version = st.segmented_control(
        "Address family",
        ["IPv4", "IPv6"],
        default="IPv4",
        key=f"{key_prefix}-family",
    )
    if version == "IPv6":
        rows = v6_cheat_rows()
        st.dataframe(
            display_rows(rows),
            hide_index=True,
            width="stretch",
            height=min(max_height, 60 + len(rows) * 35),
            alt="IPv6 prefix cheat sheet",
        )
    else:
        rows = v4_cheat_rows()
        st.dataframe(
            display_rows(rows),
            hide_index=True,
            width="stretch",
            height=min(max_height, 60 + len(rows) * 35),
            alt="IPv4 prefix cheat sheet",
        )


# ---------------------------------------------------------------------------
# Planner helpers
# ---------------------------------------------------------------------------


def read_uploaded_json(uploaded: Any) -> dict[str, Any]:
    try:
        return json.loads(uploaded.getvalue().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputError(f"Could not read JSON: {exc}") from exc


def upload_plan(
    *,
    key: str,
    on_load: "callable",
    label: str = "Import plan JSON",
) -> None:
    uploaded = st.file_uploader(label, type=["json"], key=key)
    if uploaded is None:
        return
    fingerprint = getattr(uploaded, "file_id", None) or f"{uploaded.name}:{uploaded.size}"
    marker = f"{key}-loaded"
    if st.session_state.get(marker) == fingerprint:
        return
    try:
        payload = read_uploaded_json(uploaded)
        on_load(payload)
        st.session_state[marker] = fingerprint
    except InputError as exc:
        input_error(exc)


def allocation_plan_rows(plan: Any) -> list[dict[str, str]]:
    from .planner import allocation_rows

    return allocation_rows(plan)


def ipam_segment_data(segments: Sequence[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for segment in segments:
        short_label = segment.label
        if segment.kind == "free":
            short_label = "Free"
        out.append(
            {
                "label": segment.label,
                "short_label": short_label,
                "cidr": str(segment.network),
                "kind": segment.kind,
                "start": segment.start_pct,
                "width": segment.width_pct,
                "size_label": format_count(segment.addresses),
            }
        )
    return out


def render_ipam(
    segments: Sequence[Any],
    *,
    parent: IPNetwork,
    allocated_pct: float,
    key: str,
) -> None:
    summary = (
        f"{allocated_pct:.1%} of {parent} allocated · "
        f"{len([s for s in segments if s.kind == 'allocated'])} allocated blocks"
    )
    ipam_bar(ipam_segment_data(segments), summary=summary, key=key)


def plan_usage_rows(plan: Any) -> list[dict[str, str]]:
    from .planner import allocation_rows

    rows = allocation_rows(plan)
    return rows


def build_plan_download(
    *,
    payload: dict[str, Any],
    rows: Sequence[dict[str, Any]],
    key_prefix: str,
    filename: str,
) -> None:
    copy_and_download(
        payload=payload,
        rows=rows,
        key_prefix=key_prefix,
        filename=filename,
        include_downloads=True,
    )


def error_and_stop(exc: Exception) -> None:
    input_error(exc)


def safe_int(value: Any, *, default: int = 0) -> int:
    try:
        if pd.isna(value):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def requirements_frame(
    rows: Sequence[tuple[str, int]] | None = None,
) -> pd.DataFrame:
    if rows is None:
        rows = [
            ("Core", 500),
            ("Access", 200),
            ("Management", 50),
            ("Point-to-point", 2),
        ]
    return pd.DataFrame(list(rows), columns=["Name", "Hosts"])


def allocations_frame(
    rows: Sequence[tuple[str, str]] | None = None,
) -> pd.DataFrame:
    if rows is None:
        rows = [
            ("Core", "10.0.0.0/24"),
            ("Access", "10.0.1.0/24"),
            ("Management", "10.0.2.0/25"),
        ]
    return pd.DataFrame(list(rows), columns=["Name", "CIDR"])
