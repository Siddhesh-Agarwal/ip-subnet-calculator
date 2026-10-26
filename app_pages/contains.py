import streamlit as st

from ipcalc import ui
from ipcalc.core import classify, parse_input
from ipcalc.netmath import addr_in_network, pairwise_relations

ui.page_header(
    "Contains / overlap",
    "Answer the two firewall-audit questions: is this IP inside that network, and do these lists overlap?",
    icon=":material/rule:",
)

mode = st.segmented_control(
    "Check",
    ["IP membership", "List overlap"],
    default="IP membership",
    key="contains-mode",
)

if mode == "IP membership":
    ip_text = st.text_input(
        "IP address",
        value="10.0.0.5",
        key="contains-ip",
        icon=":material/pin_drop:",
    )
    networks_text = st.text_area(
        "Networks to test",
        value="10.0.0.0/24\n10.0.1.0/24\n192.168.0.0/16\n2001:db8::/32",
        height=180,
        key="contains-networks",
    )
    try:
        target = parse_input(ip_text).address
    except Exception as exc:
        ui.input_error(exc)
        st.stop()
    networks = ui.parse_list(networks_text)
    if networks is None:
        st.stop()

    rows = []
    matches = []
    for network in networks:
        contains = addr_in_network(target, network)
        rows.append(
            {
                "network": str(network),
                "family": f"IPv{network.version}",
                "contains": "Yes" if contains else "No",
            }
        )
        if contains:
            matches.append(network)

    ui.render_badges(classify(target))
    if matches:
        st.success(
            f"{target} is inside {', '.join(str(network) for network in matches)}.",
            icon=":material/check_circle:",
        )
    else:
        st.warning(
            f"{target} is not inside any of the listed networks.",
            icon=":material/warning:",
        )

    st.dataframe(
        ui.display_rows(rows),
        hide_index=True,
        width="stretch",
        height=min(480, 60 + len(rows) * 35),
        key="contains-table",
        alt="IP membership results",
    )
    payload = {
        "ip": str(target),
        "networks": [str(network) for network in networks],
        "matches": [str(network) for network in matches],
    }
    ui.copy_and_download(
        payload=payload,
        rows=rows,
        key_prefix="contains",
        filename="ip-membership",
    )
else:
    left, right = st.columns(2)
    with left:
        text_a = st.text_area(
            "List A",
            value="10.0.0.0/24\n10.0.1.0/24\n10.0.8.0/22",
            height=200,
            key="overlap-a",
        )
    with right:
        text_b = st.text_area(
            "List B",
            value="10.0.0.128/25\n10.0.9.0/24\n192.168.0.0/16",
            height=200,
            key="overlap-b",
        )
    networks_a = ui.parse_list(text_a, empty_message="Add at least one network to list A.")
    networks_b = ui.parse_list(text_b, empty_message="Add at least one network to list B.")
    if networks_a is None or networks_b is None:
        st.stop()

    rows = pairwise_relations(networks_a, networks_b)
    if rows:
        st.warning(
            f"{len(rows)} overlapping pair(s) found between A and B.",
            icon=":material/warning:",
        )
    else:
        st.success("A and B do not overlap.", icon=":material/check_circle:")

    if rows:
        st.dataframe(
            ui.display_rows(rows),
            hide_index=True,
            width="stretch",
            height=min(520, 60 + len(rows) * 35),
            key="overlap-table",
            alt="Overlapping network pairs",
        )

    self_a = pairwise_relations(networks_a, networks_a, same_list=True)
    self_b = pairwise_relations(networks_b, networks_b, same_list=True)
    with st.expander("Check for overlaps within each list", icon=":material/content_copy:", expanded=False):
        if self_a or self_b:
            if self_a:
                st.subheader("List A")
                st.dataframe(
                    ui.display_rows(self_a),
                    hide_index=True,
                    width="stretch",
                    key="overlap-self-a",
                    alt="Overlaps within list A",
                )
            if self_b:
                st.subheader("List B")
                st.dataframe(
                    ui.display_rows(self_b),
                    hide_index=True,
                    width="stretch",
                    key="overlap-self-b",
                    alt="Overlaps within list B",
                )
        else:
            st.info("No internal overlaps in either list.", icon=":material/info:")

    payload = {
        "a": [str(network) for network in networks_a],
        "b": [str(network) for network in networks_b],
        "overlaps": rows,
        "self_a": self_a,
        "self_b": self_b,
    }
    ui.copy_and_download(
        payload=payload,
        rows=rows,
        key_prefix="overlap",
        filename="network-overlaps",
    )
