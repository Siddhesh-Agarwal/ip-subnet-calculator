import ipaddress

import streamlit as st

from ipcalc import ui
from ipcalc.core import format_count_compact
from ipcalc.netmath import coverage, networks_to_ranges, range_to_networks

ui.page_header(
    "Range ↔ CIDR",
    "Turn an arbitrary address range into the minimal CIDR list, or turn CIDRs back into ranges.",
    icon=":material/swap_horiz:",
)

direction = st.segmented_control(
    "Direction",
    ["Range → CIDR", "CIDR → Range"],
    default="Range → CIDR",
    key="range-direction",
)

if direction == "Range → CIDR":
    with st.container(horizontal=True, vertical_alignment="bottom"):
        start_text = st.text_input("Start address", value="10.0.0.5", key="range-start")
        end_text = st.text_input("End address", value="10.0.3.200", key="range-end")

    start = end = None
    try:
        start = ipaddress.ip_address(start_text.strip())
    except ValueError:
        st.error("Start address is not a valid IPv4 or IPv6 address.", icon=":material/error:")
    try:
        end = ipaddress.ip_address(end_text.strip())
    except ValueError:
        st.error("End address is not a valid IPv4 or IPv6 address.", icon=":material/error:")
    if start is None or end is None:
        st.stop()
    if start.version != end.version:
        st.error("Start and end must use the same IP version.", icon=":material/error:")
        st.stop()
    if int(start) > int(end):
        st.error("Start must not be greater than end.", icon=":material/error:")
        st.stop()

    networks = range_to_networks(start, end)
    addresses = int(end) - int(start) + 1
    with st.container(horizontal=True):
        st.metric("Start", str(start), border=True)
        st.metric("End", str(end), border=True)
        st.metric("Addresses", format_count_compact(addresses), border=True)
        st.metric("CIDR blocks", f"{len(networks):,}", border=True)

    st.caption(
        "This is the minimum number of aligned CIDR blocks that covers the range exactly."
    )
    ui.network_table(
        networks,
        key="range-result",
        height=min(520, 60 + len(networks) * 35),
        alt="Minimal CIDR list covering the address range",
    )
    rows = ui.network_rows(networks)
    payload = {
        "start": str(start),
        "end": str(end),
        "addresses": addresses,
        "cidrs": [str(network) for network in networks],
    }
    ui.copy_and_download(
        payload=payload,
        rows=rows,
        key_prefix="range",
        filename=f"range-{ui.slugify(str(start))}-{ui.slugify(str(end))}",
    )
else:
    text = st.text_area(
        "CIDR list (one per line)",
        value="10.0.0.0/24\n10.0.1.0/24\n10.0.2.0/23",
        height=180,
        key="range-cidrs",
    )
    networks = ui.parse_list(text, same_family=True)
    if networks is None:
        st.stop()
    # Build ranges from the actual union, not just the bounding box, so gaps are kept.
    ranges = networks_to_ranges(networks)
    address_cls = (
        ipaddress.IPv4Address if networks[0].version == 4 else ipaddress.IPv6Address
    )
    rows = [
        {
            "start": str(address_cls(start)),
            "end": str(address_cls(end)),
            "addresses": format_count_compact(end - start + 1),
        }
        for start, end in ranges
    ]
    with st.container(horizontal=True):
        st.metric("Input networks", f"{len(networks):,}", border=True)
        st.metric("Merged ranges", f"{len(ranges):,}", border=True)
        st.metric("Addresses", format_count_compact(coverage(networks)), border=True)

    st.caption(
        "Adjacent and overlapping CIDRs are merged first, so each row is a contiguous "
        "range that contains no gaps."
    )
    st.dataframe(
        ui.display_rows(rows),
        hide_index=True,
        width="stretch",
        height=min(520, 60 + len(rows) * 35),
        key="range-reverse-table",
        alt="Address ranges represented by the CIDR list",
    )
    payload = {
        "cidrs": [str(network) for network in networks],
        "ranges": rows,
        "addresses": coverage(networks),
    }
    ui.copy_and_download(
        payload=payload,
        rows=rows,
        key_prefix="range-reverse",
        filename="cidr-ranges",
    )
