import ipaddress

import streamlit as st

from ipcalc import ui
from ipcalc.core import InputError
from ipcalc.ipv6_extras import (
    nat64_extract,
    nat64_map,
    parse_mac,
    slaac_from_mac,
    solicited_node,
    solicited_node_mac,
)
from ipcalc.planner import site_plan

ui.page_header(
    "IPv6 toolkit",
    "EUI-64/SLAAC, solicited-node multicast, NAT64, and a /48 → /56 → /64 site planner.",
    icon=":material/lan:",
)


def _site_row(name: str, network, kind: str) -> dict[str, str]:
    first64 = ipaddress.IPv6Network((int(network.network_address), 64), strict=False)
    last64 = ipaddress.IPv6Network(
        (int(network.broadcast_address) - 255, 64), strict=False
    )
    return {
        "kind": kind,
        "name": name,
        "cidr": str(network),
        "first64": str(first64),
        "last64": str(last64),
        "slash64s": "256",
    }


tabs = st.tabs(["EUI-64 / SLAAC", "Solicited-node", "NAT64", "Site planner"])

with tabs[0]:
    st.subheader("Modified EUI-64 from a MAC address")
    mac_text = st.text_input("MAC address", value="00:1a:2b:3c:4d:5e", key="v6-mac")
    prefix_text = st.text_input(
        "IPv6 prefix",
        value="2001:db8:1234:5678::/64",
        key="v6-prefix",
        help="SLAAC is defined for /64 prefixes.",
    )
    try:
        mac = parse_mac(mac_text)
    except InputError as exc:
        ui.input_error(exc)
    else:
        parsed_prefix = ui.parse_one(prefix_text)
        if parsed_prefix is not None:
            if parsed_prefix.version != 6:
                st.error("The prefix must be IPv6.", icon=":material/error:")
            else:
                result = slaac_from_mac(parsed_prefix.network, mac)
                flags = []
                if mac.multicast:
                    flags.append("multicast bit set (not a unicast MAC)")
                if mac.locally_administered:
                    flags.append("locally administered")
                if flags:
                    st.warning("MAC flags: " + ", ".join(flags), icon=":material/warning:")
                st.caption(
                    "The U/L bit is flipped and ff:fe is inserted to form the "
                    "64-bit interface ID. The same ID is used for the link-local address."
                )
                ui.field_grid(
                    [
                        ("Normalized MAC", mac.normalized),
                        ("Modified EUI-64", result.interface_id),
                        ("SLAAC address", str(result.address)),
                        ("Link-local address", str(result.link_local)),
                        ("Prefix", str(parsed_prefix.network)),
                    ],
                    key_prefix="v6-eui",
                    columns=3,
                )
                if result.note:
                    st.info(result.note, icon=":material/info:")

with tabs[1]:
    st.subheader("Solicited-node multicast")
    addr_text = st.text_input("IPv6 unicast address", value="2001:db8::1", key="v6-sn-addr")
    parsed = ui.parse_one(addr_text)
    if parsed is not None:
        if parsed.version != 6:
            st.error("Enter an IPv6 address.", icon=":material/error:")
        else:
            multicast = solicited_node(parsed.address)
            ui.field_grid(
                [
                    ("Unicast address", str(parsed.address)),
                    ("Solicited-node multicast", str(multicast)),
                    ("Multicast MAC", solicited_node_mac(parsed.address)),
                ],
                key_prefix="v6-sn",
                columns=3,
            )
            st.caption(
                "The solicited-node address is ff02::1:ff00:0/104 plus the low "
                "24 bits of the unicast address. The multicast MAC is 33:33 "
                "followed by those same 24 bits."
            )

with tabs[2]:
    st.subheader("NAT64 / 64:ff9b::/96")
    left, right = st.columns(2)
    with left:
        st.markdown("**IPv4 → IPv6**")
        v4_text = st.text_input("IPv4 address", value="192.0.2.33", key="nat64-v4")
        nat_prefix_text = st.text_input(
            "NAT64 prefix",
            value="64:ff9b::/96",
            key="nat64-prefix",
        )
        parsed_prefix = ui.parse_one(nat_prefix_text)
        if parsed_prefix is not None:
            if parsed_prefix.version != 6 or parsed_prefix.prefixlen != 96:
                st.error("The NAT64 prefix must be an IPv6 /96.", icon=":material/error:")
            else:
                try:
                    v4 = ipaddress.IPv4Address(v4_text.strip())
                except ValueError:
                    ui.input_error(InputError("Enter a valid IPv4 address."))
                else:
                    mapped = nat64_map(v4, parsed_prefix.network)
                    ui.copy_field("Mapped IPv6", str(mapped), key="nat64-mapped")
    with right:
        st.markdown("**IPv6 → IPv4**")
        v6_text = st.text_input(
            "IPv6 address in the NAT64 prefix",
            value="64:ff9b::c000:221",
            key="nat64-v6",
        )
        parsed_v6 = ui.parse_one(v6_text)
        if parsed_v6 is not None:
            if parsed_v6.version != 6:
                st.error("Enter an IPv6 address.", icon=":material/error:")
            elif parsed_prefix is not None and parsed_prefix.version == 6:
                extracted = nat64_extract(parsed_v6.address, parsed_prefix.network)
                if extracted is None:
                    st.info(
                        f"{parsed_v6.address} is not inside {parsed_prefix.network}.",
                        icon=":material/info:",
                    )
                else:
                    ui.copy_field("Extracted IPv4", str(extracted), key="nat64-extracted")
    st.caption(
        "This simplified mapping is for a /96 prefix. 64:ff9b::/96 is the "
        "well-known RFC 6052 NAT64 prefix."
    )

with tabs[3]:
    st.subheader("IPv6 site planner")
    parent_text = st.text_input(
        "Parent /48",
        value="2001:db8:1000::/48",
        key="site-parent",
        help="Each /48 contains 256 /56 sites and 65,536 /64s.",
    )
    parsed_parent = ui.parse_one(parent_text)
    if parsed_parent is not None:
        if parsed_parent.version != 6 or parsed_parent.prefixlen != 48:
            st.error("The site planner expects an IPv6 /48.", icon=":material/error:")
        else:
            parent = parsed_parent.network
            st.caption(
                "Each site is a /56. Inside each site there are 256 /64 LANs."
            )
            edited = st.data_editor(
                ui.allocations_frame(
                    [
                        ("HQ", "2001:db8:1000::/56"),
                        ("Branch", "2001:db8:1000:100::/56"),
                        ("Lab", "2001:db8:1000:200::/56"),
                    ]
                ),
                num_rows="dynamic",
                hide_index=True,
                width="stretch",
                key="site-editor",
                column_config={
                    "Name": st.column_config.TextColumn("Name", width="medium"),
                    "CIDR": st.column_config.TextColumn("/56 CIDR", width="medium"),
                },
                alt="IPv6 /56 site allocations",
            )
            allocations = []
            for index, row in edited.iterrows():
                cidr = str(row.get("CIDR") or "").strip()
                if not cidr or cidr.lower() == "nan":
                    continue
                name = str(row.get("Name") or "").strip() or f"Site {index + 1}"
                try:
                    parsed_site = ui.parse_one(cidr)
                except Exception:
                    continue
                if parsed_site is not None:
                    allocations.append((name, parsed_site.network))

            try:
                plan = site_plan(parent, allocations)
            except InputError as exc:
                ui.input_error(exc)
            else:
                for warning in plan["warnings"]:
                    st.warning(warning, icon=":material/warning:")
                with st.container(horizontal=True):
                    st.metric("Sites (/56)", f"{plan['total_sites']:,}", border=True)
                    st.metric("Used", f"{plan['used_sites']:,}", border=True)
                    st.metric("Free", f"{plan['free_sites']:,}", border=True)
                    st.metric("/64s", f"{plan['total_slash64']:,}", border=True)

                rows = []
                for name, network in plan["used"]:
                    rows.append(_site_row(name, network, "Allocated"))
                for network in plan["free"]:
                    rows.append(_site_row("Free", network, "Free"))
                st.dataframe(
                    ui.display_rows(rows),
                    hide_index=True,
                    width="stretch",
                    height=min(520, 60 + len(rows) * 35),
                    key="site-table",
                    alt="IPv6 /56 site allocation table",
                )
                payload = {
                    "parent": str(parent),
                    "sites": rows,
                    "used_sites": plan["used_sites"],
                    "free_sites": plan["free_sites"],
                    "slash64_per_site": plan["slash64_per_site"],
                    "total_slash64": plan["total_slash64"],
                }
                ui.copy_and_download(
                    payload=payload,
                    rows=rows,
                    key_prefix="site",
                    filename="ipv6-site-plan",
                )
