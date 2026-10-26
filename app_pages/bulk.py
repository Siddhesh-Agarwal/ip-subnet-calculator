import streamlit as st

from ipcalc import ui
from ipcalc.core import bulk_rows

ui.page_header(
    "Bulk analyzer",
    "Paste hundreds of addresses or networks and filter the parsed result.",
    icon=":material/table_view:",
)

DEFAULT = """10.0.0.5/24
192.168.1.10 255.255.255.0
172.16.4.0/22
100.64.0.1/10
203.0.113.8/29
2001:db8::1/64
2001:db8:1234::/48
"""

text = st.text_area(
    "One address or network per line",
    value=DEFAULT,
    height=220,
    key="bulk-input",
    help="Blank lines and `#` comments are ignored. Host bits are normalized.",
)

if not text.strip():
    st.info("Paste one address or network per line.", icon=":material/info:")
    st.stop()


@st.cache_data(ttl="5m", max_entries=32)
def parse_bulk(raw: str):
    return bulk_rows(raw)


rows, errors = parse_bulk(text)
if not rows:
    st.info("No usable lines were found.", icon=":material/info:")
    st.stop()

v4 = sum(1 for row in rows if row["family"] == "IPv4")
v6 = sum(1 for row in rows if row["family"] == "IPv6")
normalized = sum(1 for row in rows if row["status"] == "normalized")

with st.container(horizontal=True):
    st.metric("Rows", f"{len(rows):,}", border=True)
    st.metric("IPv4", f"{v4:,}", border=True)
    st.metric("IPv6", f"{v6:,}", border=True)
    st.metric("Normalized", f"{normalized:,}", border=True)
    st.metric("Errors", f"{len(errors):,}", border=True)

if errors:
    st.warning(
        f"{len(errors)} line(s) could not be parsed. They remain in the table "
        "with an error status so you can find them quickly.",
        icon=":material/warning:",
    )

with st.container(horizontal=True, vertical_alignment="bottom"):
    query = st.text_input(
        "Filter",
        key="bulk-filter",
        placeholder="Filter by address, network, or type",
        icon=":material/filter_alt:",
        label_visibility="collapsed",
    )
    family = st.segmented_control(
        "Family",
        ["All families", "IPv4", "IPv6"],
        default="All families",
        key="bulk-family",
        label_visibility="collapsed",
    )
    status = st.segmented_control(
        "Status",
        ["All statuses", "ok", "normalized", "error"],
        default="All statuses",
        key="bulk-status",
        label_visibility="collapsed",
    )

filtered = rows
if family and family != "All families":
    filtered = [row for row in filtered if row["family"] == family]
if status and status != "All statuses":
    filtered = [row for row in filtered if row["status"] == status]
if query and query.strip():
    needle = query.strip().lower()
    filtered = [
        row
        for row in filtered
        if needle in " ".join(str(value) for value in row.values()).lower()
    ]

if not filtered:
    st.info("No rows match the current filter.", icon=":material/search_off:")
else:
    display = []
    for index, row in enumerate(filtered, start=1):
        display.append({"#": str(index), **row})
    st.dataframe(
        ui.display_rows(display),
        hide_index=True,
        width="stretch",
        height=min(520, 60 + len(display) * 35),
        key="bulk-table",
        alt="Parsed bulk address table",
    )

st.space("small")
ui.copy_and_download(
    payload={"rows": filtered, "errors": errors},
    rows=filtered,
    key_prefix="bulk",
    filename="bulk-analysis",
)
