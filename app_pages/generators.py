import ipaddress

import streamlit as st

from ipcalc import ui
from ipcalc.core import host_info
from ipcalc.generators import (
    acl_wildcard,
    cisco_acl,
    cisco_acl_entries,
    cisco_interface,
    cloud_rows,
    juniper_interface,
    linux_interface,
    suggested_host,
)

ui.page_header(
    "Config generators",
    "Copy-ready interface, ACL, and cloud subnet snippets.",
    icon=":material/code:",
)

input_text = st.text_input(
    "Network",
    value="10.0.0.0/24",
    key="gen-input",
    icon=":material/router:",
)
parsed = ui.parse_one(input_text)
if parsed is None:
    st.stop()

default_host = suggested_host(parsed)
with st.container(horizontal=True, vertical_alignment="bottom"):
    host_text = st.text_input(
        "Example host address",
        value=default_host,
        key=f"gen-host-{parsed.normalized}",
        help="Used in the interface snippets; it does not have to be the first host.",
    )
    interface = st.text_input(
        "Cisco interface",
        value="GigabitEthernet0/1",
        key="gen-interface",
    )
    description = st.text_input(
        "Description",
        value="Uplink",
        key="gen-description",
    )
    dev = st.text_input("Linux device", value="eth0", key="gen-dev")

try:
    host_address = ipaddress.ip_address(host_text.strip())
except ValueError:
    host_address = None
    st.warning("Example host is not a valid IP address; using the first usable host.", icon=":material/warning:")
if host_address is not None and host_address.version != parsed.version:
    st.warning("Example host family does not match the network; using the first usable host.", icon=":material/warning:")
    host_address = None
if host_address is not None and host_address not in parsed.network:
    st.warning(
        f"{host_address} is outside {parsed.network}; the snippet will still use it.",
        icon=":material/warning:",
    )
host = str(host_address) if host_address is not None else default_host

cisco = cisco_interface(
    parsed, interface=interface, description=description, host=host
)
juniper = juniper_interface(
    parsed, description=description, host=host
)
linux = linux_interface(parsed, dev=dev, host=host)
acl = cisco_acl(parsed)
cloud = cloud_rows(parsed)

tabs = st.tabs(["Cisco", "Juniper", "Linux", "ACL", "Cloud"])
with tabs[0]:
    st.subheader("Interface")
    st.code(cisco, language="text")
    st.subheader("ACL")
    st.code(acl, language="text")
with tabs[1]:
    st.code(juniper, language="bash")
with tabs[2]:
    st.code(linux, language="bash")
with tabs[3]:
    st.subheader("Wildcard / prefix")
    ui.copy_field("Wildcard mask", acl_wildcard(parsed), key="gen-wildcard")
    st.space("small")
    ui.copy_field("ACL entry", cisco_acl_entries(parsed), key="gen-acl-entry")
    st.caption(
        "IPv4 ACLs use a wildcard mask. IPv6 ACLs use a prefix and do not have "
        "a wildcard mask."
    )
with tabs[4]:
    st.dataframe(
        ui.display_rows(cloud),
        hide_index=True,
        width="stretch",
        alt="Cloud provider reserved address rules",
    )
    st.caption(
        "Reserved-address rules change over time. Verify against the provider's "
        "current documentation before using them in production."
    )

payload = {
    "network": str(parsed.network),
    "host": host,
    "cisco": cisco,
    "cisco_acl": acl,
    "juniper": juniper,
    "linux": linux,
    "acl_wildcard": acl_wildcard(parsed),
    "cloud": cloud,
}
rows = [
    {"target": "Cisco", "snippet": cisco},
    {"target": "Juniper", "snippet": juniper},
    {"target": "Linux", "snippet": linux},
    {"target": "ACL", "snippet": acl},
]
st.space("small")
ui.copy_and_download(
    payload=payload,
    rows=rows,
    key_prefix="gen",
    filename="config-snippets",
)
