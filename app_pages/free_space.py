import streamlit as st

from ipcalc import ui
from ipcalc.core import format_count, host_info
from ipcalc.netmath import coverage, largest_network
from ipcalc.planner import free_space

ui.page_header(
    "Free-space finder",
    "Give a parent block and the subnets already in use; see the gaps that remain.",
    icon=":material/space_dashboard:",
)

DEFAULT_USED = """10.0.0.0/24
10.0.1.0/24
10.0.4.0/22
10.0.8.0/23
"""

parent_text = st.text_input(
    "Parent block",
    value="10.0.0.0/16",
    key="free-parent",
    icon=":material/hub:",
)
parsed = ui.parse_one(parent_text)
if parsed is None:
    st.stop()
parent = parsed.network

used_text = st.text_area(
    "Used subnets (one per line)",
    value=DEFAULT_USED,
    height=180,
    key="free-used",
    help="Blank lines and `#` comments are ignored.",
)

used = ui.parse_list(used_text, empty_message="Add the subnets that are already in use.")
if used is None:
    st.stop()

gaps, warnings = free_space(parent, used)
for warning in warnings:
    st.warning(warning, icon=":material/warning:")

used_inside = [
    network for network in used if network.version == parent.version and network.subnet_of(parent)
]
used_coverage = coverage(used_inside)
free_coverage = sum(network.num_addresses for network in gaps)
largest = largest_network(gaps)

with st.container(horizontal=True):
    st.metric("Parent", str(parent), border=True)
    st.metric("Used", format_count(used_coverage), border=True)
    st.metric("Free", format_count(free_coverage), border=True)
    st.metric("Gaps", f"{len(gaps):,}", border=True)

if largest is not None:
    info = host_info(largest)
    with st.container(border=True):
        st.subheader("Largest free block")
        st.caption(
            "This is the biggest contiguous CIDR available in the parent. "
            "Use it first when you add a new subnet."
        )
        with st.container(horizontal=True):
            ui.copy_field(
                "Largest free block",
                str(largest),
                key="free-largest-cidr",
            )
        st.caption(
            f"{format_count(largest.num_addresses)} addresses · "
            f"{info.usable_label} usable hosts"
        )
else:
    st.success("No free space remains in this parent block.", icon=":material/check_circle:")

st.subheader("Free gaps")
if gaps:
    rows = []
    for index, network in enumerate(gaps, start=1):
        row = ui.network_rows([network], numbered=False)[0]
        rows.append(
            {
                "#": str(index),
                **row,
                "notes": "Largest" if network == largest else "",
            }
        )
    st.dataframe(
        ui.display_rows(rows),
        hide_index=True,
        width="stretch",
        height=min(480, 60 + len(rows) * 35),
        key="free-table",
        alt="Free gaps inside the parent block",
    )
else:
    st.info("No gaps — the parent is fully covered by the used list.", icon=":material/info:")

with st.expander("Used networks", icon=":material/list:", expanded=False):
    ui.network_table(used, key="free-used-table", alt="Subnets already in use")

payload = {
    "parent": str(parent),
    "used": [str(network) for network in used],
    "free": [str(network) for network in gaps],
    "largest_free": str(largest) if largest is not None else None,
}
rows = ui.network_rows(gaps)
st.space("small")
ui.copy_and_download(
    payload=payload,
    rows=rows,
    key_prefix="free",
    filename=f"free-space-{ui.slugify(str(parent))}",
)
