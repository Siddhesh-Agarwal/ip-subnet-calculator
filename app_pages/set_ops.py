import streamlit as st

from ipcalc import ui
from ipcalc.core import InputError, format_count
from ipcalc.netmath import (
    coverage,
    intersect_networks,
    subtract_networks,
    union_networks,
)

ui.page_header(
    "Set operations",
    "Union, intersect, and subtract prefix lists to build allowlists or find what is left of a block.",
    icon=":material/set_meal:",
)

left, right = st.columns(2)
with left:
    text_a = st.text_area(
        "List A",
        value="10.0.0.0/24\n10.0.1.0/24\n10.0.2.0/24",
        height=190,
        key="set-a",
    )
with right:
    text_b = st.text_area(
        "List B",
        value="10.0.0.128/25\n10.0.2.0/24",
        height=190,
        key="set-b",
    )

networks_a = ui.parse_list(text_a, empty_message="Add at least one network to list A.")
networks_b = ui.parse_list(text_b, empty_message="Add at least one network to list B.")
if networks_a is None or networks_b is None:
    st.stop()

operation = st.segmented_control(
    "Operation",
    ["A ∪ B", "A ∩ B", "A − B", "B − A"],
    default="A ∪ B",
    key="set-operation",
    help="Subtraction returns the minimal CIDR list for the remaining space.",
)

try:
    if operation == "A ∪ B":
        result = union_networks(networks_a, networks_b)
        label = "Union"
        explanation = "Every address in either list, collapsed to the minimal CIDR set."
    elif operation == "A ∩ B":
        result = intersect_networks(networks_a, networks_b)
        label = "Intersection"
        explanation = "Only addresses present in both lists."
    elif operation == "A − B":
        result = subtract_networks(networks_a, networks_b)
        label = "A minus B"
        explanation = "Addresses in A that are not covered by any network in B."
    else:
        result = subtract_networks(networks_b, networks_a)
        label = "B minus A"
        explanation = "Addresses in B that are not covered by any network in A."
except InputError as exc:
    st.error(str(exc), icon=":material/error:")
    st.stop()

with st.container(horizontal=True):
    st.metric("Operation", label, border=True)
    st.metric("Result prefixes", f"{len(result):,}", border=True)
    st.metric("Result addresses", format_count(coverage(result)), border=True)
    st.metric(
        "A + B addresses",
        format_count(coverage(networks_a) + coverage(networks_b)),
        border=True,
        help="Sum of both input lists; overlapping space is counted twice.",
    )

st.caption(explanation)
st.space("small")

if result:
    ui.network_table(
        result,
        key="set-result",
        height=min(520, 60 + len(result) * 35),
        alt="Result of the prefix-list set operation",
    )
else:
    st.info("The result is empty.", icon=":material/info:")

payload = {
    "operation": operation,
    "a": [str(network) for network in networks_a],
    "b": [str(network) for network in networks_b],
    "result": [str(network) for network in result],
    "result_addresses": coverage(result),
}
rows = ui.network_rows(result)
ui.copy_and_download(
    payload=payload,
    rows=rows,
    key_prefix="set",
    filename=f"set-{ui.slugify(operation)}",
)
