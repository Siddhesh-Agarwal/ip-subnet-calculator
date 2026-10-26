import streamlit as st

from ipcalc import ui
from ipcalc.core import InputError
from ipcalc.dns import (
    ptr_records,
    reverse_pointer,
    rfc2317_snippets,
    zone_for_network,
    zone_hierarchy,
    zone_snippet,
)

ui.page_header(
    "Reverse DNS",
    "in-addr.arpa and ip6.arpa pointers, zone snippets, and RFC 2317 classless delegation.",
    icon=":material/dns:",
)

input_text = st.text_input(
    "Network or address",
    value="192.0.2.0/25",
    key="dns-input",
    icon=":material/language:",
    help="Try 192.0.2.0/25 to see an RFC 2317 delegation.",
)
parsed = ui.parse_one(input_text)
if parsed is None:
    st.stop()

with st.container(horizontal=True, vertical_alignment="bottom"):
    domain = st.text_input("Domain suffix", value="example.com", key="dns-domain")
    nameserver = st.text_input("Primary nameserver", value="ns1.example.net", key="dns-ns1")
    second = st.text_input("Secondary nameserver", value="ns2.example.net", key="dns-ns2")

network = parsed.network
info = zone_for_network(network)

address_pointer = reverse_pointer(parsed.address)
start_pointer = reverse_pointer(network.network_address)
with st.container(horizontal=True):
    ui.copy_field("Reverse zone", info.zone, key="dns-zone")
    ui.copy_field("Address pointer", address_pointer, key="dns-pointer")
    if start_pointer != address_pointer:
        ui.copy_field("Network start pointer", start_pointer, key="dns-start")

if info.warning:
    if info.aligned:
        st.info(info.warning, icon=":material/info:")
    else:
        st.warning(info.warning, icon=":material/warning:")

for line in zone_hierarchy(network)[1:]:
    if line != info.warning:
        st.caption(line)

st.space("small")
st.subheader("Zone snippet")
snippet = zone_snippet(
    network,
    domain=domain,
    nameserver=nameserver,
    limit=16,
)
st.code(snippet, language="text")
st.caption(
    "PTR records are limited to the first 16 addresses. Use $GENERATE for larger "
    "zones; the RFC 2317 snippets below use it."
)

if info.rfc2317:
    st.subheader("RFC 2317 classless delegation")
    try:
        parent_snippet, child_snippet = rfc2317_snippets(
            network,
            domain=domain,
            nameserver=nameserver,
            second_nameserver=second,
        )
    except InputError as exc:
        ui.input_error(exc)
    else:
        st.caption("Parent zone: delegation and CNAME records")
        st.code(parent_snippet, language="text")
        st.caption("Child zone: authoritative PTR records")
        st.code(child_snippet, language="text")

st.subheader("PTR records (first 16)")
records = ptr_records(network, domain, limit=16)
if records:
    st.dataframe(
        ui.display_rows(records),
        hide_index=True,
        width="stretch",
        height=min(480, 60 + len(records) * 35),
        key="dns-ptr-table",
        alt="PTR records for the first addresses in the network",
    )
else:
    st.info("No PTR records generated.", icon=":material/info:")

payload = {
    "network": str(network),
    "zone": info.zone,
    "aligned": info.aligned,
    "rfc2317": info.rfc2317,
    "zone_snippet": snippet,
    "ptr_records": records,
}
st.space("small")
ui.copy_and_download(
    payload=payload,
    rows=records,
    key_prefix="dns",
    filename="reverse-dns",
)
