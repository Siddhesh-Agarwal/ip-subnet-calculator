from urllib.parse import urlencode

import streamlit as st

from ipcalc import ui
from ipcalc.components import copy_button

ui.page_header(
    "Subnet calculator",
    "One input, automatic format detection, and a result panel built for copy/paste.",
    icon=":material/calculate:",
)

value = st.text_input(
    "Address or network",
    value="10.0.0.5/24",
    key="q",
    bind="query-params",
    placeholder="10.0.0.5/24 · 10.0.0.5 255.255.255.0 · 2001:db8::1/64",
    help=(
        "Accepts CIDR, a dotted netmask, a wildcard mask, or a bare address. "
        "Bare addresses are treated as /32 (IPv4) or /128 (IPv6)."
    ),
    icon=":material/route:",
)

st.caption(
    "The address is kept in the URL as `?q=…`, so a result can be pasted into "
    "a ticket or chat. Host bits in the input are flagged and normalized."
)

if value.strip():
    parsed = ui.parse_one(value)
    if parsed is not None:
        ui.render_result(parsed, key_prefix="calc")
else:
    st.info(
        "Enter an address to calculate its network. Try `10.0.0.5/24`, "
        "`10.0.0.5 255.255.255.0`, `10.0.0.5 0.0.0.255`, or "
        "`2001:db8::1/64`.",
        icon=":material/info:",
    )

st.space("medium")
with st.expander(
    "Prefix cheat sheet",
    icon=":material/table_chart:",
    on_change="rerun",
) as cheat:
    if cheat.open:
        ui.render_cheat_sheet(key_prefix="calc-cheat", max_height=700)

st.space("small")
st.caption(
    "Copy the query string, or copy the browser address bar for a complete "
    "shareable link."
)
copy_button(
    "Copy query string",
    "?" + urlencode({"q": value.strip()}),
    key="calc-copy-query",
)
