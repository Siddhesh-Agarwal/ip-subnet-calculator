import streamlit as st

st.set_page_config(
    page_title="IP Subnet Calculator",
    page_icon=":material/hub:",
    layout="wide",
    initial_sidebar_state="expanded",
)

navigation = st.navigation(
    {
        "Analyze": [
            st.Page(
                "app_pages/calculator.py",
                title="Calculator",
                icon=":material/calculate:",
                default=True,
            ),
            st.Page(
                "app_pages/bulk.py",
                title="Bulk analyzer",
                icon=":material/table_view:",
            ),
            st.Page(
                "app_pages/cheat_sheet.py",
                title="Prefix cheat sheet",
                icon=":material/menu_book:",
            ),
        ],
        "Plan": [
            st.Page(
                "app_pages/splitter.py",
                title="Subnet splitter",
                icon=":material/call_split:",
            ),
            st.Page(
                "app_pages/vlsm.py",
                title="VLSM planner",
                icon=":material/account_tree:",
            ),
            st.Page(
                "app_pages/free_space.py",
                title="Free space",
                icon=":material/space_dashboard:",
            ),
            st.Page(
                "app_pages/ipam.py",
                title="IPAM map",
                icon=":material/bar_chart:",
            ),
            st.Page(
                "app_pages/ipv6_toolkit.py",
                title="IPv6 toolkit",
                icon=":material/lan:",
            ),
        ],
        "Operate": [
            st.Page(
                "app_pages/summarize.py",
                title="Summarization",
                icon=":material/compress:",
            ),
            st.Page(
                "app_pages/range_cidr.py",
                title="Range ↔ CIDR",
                icon=":material/swap_horiz:",
            ),
            st.Page(
                "app_pages/contains.py",
                title="Contains / overlap",
                icon=":material/rule:",
            ),
            st.Page(
                "app_pages/set_ops.py",
                title="Set operations",
                icon=":material/set_meal:",
            ),
            st.Page(
                "app_pages/generators.py",
                title="Config generators",
                icon=":material/code:",
            ),
            st.Page(
                "app_pages/reverse_dns.py",
                title="Reverse DNS",
                icon=":material/dns:",
            ),
        ],
    }
)

navigation.run()
