import streamlit as st

from ipcalc import ui
from ipcalc.core import format_count
from ipcalc.netmath import (
    covering_supernet,
    coverage,
    subtract_networks,
    summarize_networks,
)

ui.page_header(
    "Summarization",
    "Collapse a list of networks, or find the smallest single supernet and see what it over-covers.",
    icon=":material/compress:",
)

DEFAULT = """10.0.0.0/24
10.0.1.0/24
10.0.2.0/23
10.0.4.0/24
"""

text = st.text_area(
    "Networks to summarize",
    value=DEFAULT,
    height=180,
    key="summarize-input",
    help="One network per line. Overlaps are merged; host bits are normalized.",
)
networks = ui.parse_list(text)
if networks is None:
    st.stop()

mode = st.segmented_control(
    "Summary style",
    ["Exact minimal set", "Single supernet"],
    default="Exact minimal set",
    key="summarize-mode",
    help=(
        "Exact keeps every address in the input. Single supernet is shorter but "
        "can cover gaps between the listed networks."
    ),
)

input_coverage = coverage(networks)
if mode == "Single supernet":
    supernet = covering_supernet(networks)
    if supernet is None:
        st.info("No networks to summarize.", icon=":material/info:")
        st.stop()
    result = [supernet]
    extra = subtract_networks([supernet], networks)
    extra_count = max(0, coverage([supernet]) - input_coverage)
    summary_label = "Single covering prefix"
else:
    summary = summarize_networks(networks)
    result = summary["networks"]
    extra = summary["extra"]
    extra_count = summary["extra_count"]
    summary_label = "Minimal CIDR set"

summary_coverage = coverage(result)

with st.container(horizontal=True):
    st.metric("Input networks", f"{len(networks):,}", border=True)
    st.metric("Result prefixes", f"{len(result):,}", border=True)
    st.metric("Input addresses", format_count(input_coverage), border=True)
    st.metric("Result addresses", format_count(summary_coverage), border=True)
    st.metric("Extra addresses", format_count(extra_count), border=True)

if extra_count:
    st.warning(
        f"{summary_label} covers **{format_count(extra_count)}** addresses that "
        "were not in the input list. The extra ranges are shown below.",
        icon=":material/warning:",
    )
else:
    st.success(
        f"{summary_label} covers exactly the same address space as the input.",
        icon=":material/check_circle:",
    )

st.subheader("Summary result")
ui.network_table(
    result,
    key="summarize-result",
    height=min(480, 60 + len(result) * 35),
    alt="Summarized network result",
)

if extra:
    st.subheader("Address space added by the summary")
    ui.network_table(
        extra,
        key="summarize-extra",
        height=min(360, 60 + len(extra) * 35),
        alt="Extra address space covered by the summary",
    )

with st.expander("Input networks", icon=":material/list:", expanded=False):
    ui.network_table(
        networks,
        key="summarize-input-table",
        alt="Original input networks",
    )

payload = {
    "mode": mode,
    "input": [str(network) for network in networks],
    "summary": [str(network) for network in result],
    "extra": [str(network) for network in extra],
    "input_addresses": input_coverage,
    "summary_addresses": summary_coverage,
    "extra_addresses": extra_count,
}
rows = ui.network_rows(result)
st.space("small")
ui.copy_and_download(
    payload=payload,
    rows=rows,
    key_prefix="summarize",
    filename="summarized-networks",
)
