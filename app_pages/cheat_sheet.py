import streamlit as st

from ipcalc import ui

ui.page_header(
    "Prefix cheat sheet",
    "The mask, host count, and common use for every IPv4 prefix and the IPv6 prefixes that matter.",
    icon=":material/menu_book:",
)

ui.render_cheat_sheet(key_prefix="cheat-page")

st.space("medium")
st.subheader("Number rules used here")
st.markdown(
    """
- IPv4 usable hosts are `2^(32-prefix) - 2` for /0–/30, because the network and broadcast addresses are reserved.
- IPv4 **/31** follows RFC 3021: both addresses are usable and there is no broadcast address.
- IPv4 **/32** is a single host route; that one address is usable.
- IPv6 has no broadcast address, so all addresses in a prefix are counted as usable.
- IPv6 **/127** follows RFC 6164 (point-to-point), and **/128** is a single host.
- Large IPv6 counts are shown as powers of two as well as decimal integers, so `2^64 = 18,446,744,073,709,551,616` is explicit rather than rounded.
"""
)
