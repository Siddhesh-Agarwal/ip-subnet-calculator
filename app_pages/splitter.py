import streamlit as st

from ipcalc import ui
from ipcalc.core import InputError, format_count, host_info
from ipcalc.planner import (
    hosts_for_prefix,
    split_by_count,
    split_by_hosts,
    split_by_prefix,
)
from ipcalc.core import parse_input

ui.page_header(
    "Subnet splitter",
    "Split a block by prefix, subnet count, or minimum hosts per subnet.",
    icon=":material/call_split:",
)

parent_text = st.text_input(
    "Parent block",
    value="10.0.0.0/16",
    key="split_parent",
    bind="query-params",
    icon=":material/hub:",
    help="Accepts any address/prefix form, including IPv6.",
)
parsed = ui.parse_one(parent_text)
if parsed is None:
    st.stop()

if parsed.host_bits_set:
    st.warning(
        f"Host bits set in the parent; using {parsed.normalized}.",
        icon=":material/warning:",
    )

parent = parsed.network
max_prefix = 32 if parent.version == 4 else 128
min_prefix = parent.prefixlen

st.space("small")
mode = st.segmented_control(
    "Split method",
    ["By new prefix", "By subnet count", "By minimum hosts"],
    default="By new prefix",
    key="split-mode",
)

limit = 4096
result = None
note = ""
try:
    if mode == "By new prefix":
        default_prefix = min(max_prefix, min_prefix + 4)
        new_prefix = st.number_input(
            "New prefix length",
            min_value=min_prefix,
            max_value=max_prefix,
            value=default_prefix,
            step=1,
            key=f"split-prefix-{min_prefix}-{max_prefix}",
            help=f"The parent is /{min_prefix}; choose a longer prefix.",
        )
        result = split_by_prefix(parent, int(new_prefix), limit=limit)
        note = (
            f"{len(result):,} subnets of /{int(new_prefix)}. "
            f"Each has {format_count(hosts_for_prefix(int(new_prefix), parent.version))} "
            "usable addresses."
        )
    elif mode == "By subnet count":
        count = st.number_input(
            "Number of subnets",
            min_value=1,
            max_value=limit,
            value=4,
            step=1,
            key="split-count",
            help=f"Counts are rounded up to a power of two (limit {limit:,}).",
        )
        split = split_by_count(parent, int(count), limit=limit)
        result = split.networks
        note = split.note or (
            f"{len(result):,} subnets of /{split.new_prefix}."
        )
    else:
        hosts = st.number_input(
            "Minimum usable hosts per subnet",
            min_value=1,
            max_value=1_000_000_000,
            value=50,
            step=1,
            key="split-hosts",
            help=(
                "IPv4 /31 and /32 follow RFC 3021 and host-route rules. "
                "IPv6 uses every address in the prefix."
            ),
        )
        split = split_by_hosts(parent, int(hosts), limit=limit)
        result = split.networks
        note = split.note or (
            f"{len(result):,} subnets of /{split.new_prefix}."
        )
except InputError as exc:
    st.error(str(exc), icon=":material/error:")
    st.stop()

if result is None:
    st.stop()

info = host_info(result[0]) if result else None
with st.container(horizontal=True):
    st.metric("Child prefix", f"/{result[0].prefixlen}" if result else "—", border=True)
    st.metric("Subnets", f"{len(result):,}", border=True)
    st.metric(
        "Usable per subnet",
        info.usable_label if info else "—",
        border=True,
    )
    st.metric(
        "Addresses covered",
        format_count(sum(network.num_addresses for network in result)),
        border=True,
    )

st.caption(note)
st.space("small")

ui.network_table(
    result,
    key="split-table",
    height=520,
    alt="Table of subnet split results",
)

rows = ui.network_rows(result)
payload = {
    "parent": str(parent),
    "method": mode,
    "subnet_count": len(result),
    "subnets": rows,
}
st.space("small")
ui.copy_and_download(
    payload=payload,
    rows=rows,
    key_prefix="split",
    filename=f"split-{ui.slugify(str(parent))}",
)
